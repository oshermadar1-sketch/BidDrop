//! PoBA worker – pulls market, computes IDA*-like assignment LOCALLY in Rust,
//! then asks backend to submit signed extrinsics (submit_proposal),
//! and *optionally* asks backend to finalize a nearby slot.
//!
//! Multi-node behavior:
//!  - Every authority node runs this worker and computes its own proposal.
//!  - Each node should have a unique POBA_PROPOSER_ID (e.g. "alice", "bob").
//!  - Only nodes with POBA_ROLE=finalizer will also call /poba/finalize-slot.
//!
//! Finalization lag behavior:
//!  - Controlled by POBA_FINALIZE_LAG_SLOTS (u64):
//!      0 (default) → finalize the *current* slot
//!      1          → finalize slot-1 (gives more time for other proposers)

use crate::service::FullClient;
use std::{sync::Arc, time::Duration};
use sc_client_api::HeaderBackend;
use reqwest::Client as Http;
use serde::{Deserialize, Serialize};
use sp_api::ProvideRuntimeApi;
use sp_runtime::traits::SaturatedConversion; // for best_number -> u64
use log;

// ---------------------------- Market types ----------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MarketRequest {
    pub uuid_16: String,
    pub from_lat: i32,
    pub from_lon: i32,
    pub to_lat: i32,
    pub to_lon: i32,
    pub max_price_cents: u32,
    pub kind: u8, // 0 = package, 1 = passenger
    pub window_start: u64,
    pub window_end: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MarketOffer {
    pub uuid_16: String,
    pub min_price_cents: u32,
    pub from_lat: i32,
    pub from_lon: i32,
    pub to_lat: i32,
    pub to_lon: i32,
    pub window_start: u64,
    pub window_end: u64,
    pub types_mask: u32, // bit 0 = package, bit 1 = passenger
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MatchItem {
    pub request_uuid: String,
    pub offer_uuid: String,
    pub agreed_price_cents: u32,
    pub partial_score: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SubmitProposalBody {
    pub slot: u64,
    pub total_score: i64,
    pub matches: Vec<MatchItem>,
}

// ---------------------------- Helpers ----------------------------

/// Derive PoBA slot from the node's best block number.
/// This keeps slot numbers small and easy to correlate with chain state.
fn current_slot_from_client(client: &FullClient) -> u64 {
    let info = client.info();
    info.best_number.saturated_into::<u64>()
}

/// Helper to append `?proposer_id=...` to a base URL.
fn with_proposer_id(base: &str, proposer_id: &str) -> String {
    // If the base already has query params, use '&', otherwise use '?'
    if base.contains('?') {
        format!("{base}&proposer_id={}", proposer_id)
    } else {
        format!("{base}?proposer_id={}", proposer_id)
    }
}

fn env_i64(name: &str, default: i64) -> i64 {
    std::env::var(name)
        .ok()
        .and_then(|v| v.parse::<i64>().ok())
        .unwrap_or(default)
}

fn env_f64(name: &str, default: f64) -> f64 {
    std::env::var(name)
        .ok()
        .and_then(|v| v.parse::<f64>().ok())
        .unwrap_or(default)
}

fn env_bool(name: &str, default: bool) -> bool {
    std::env::var(name)
        .ok()
        .map(|v| {
            let l = v.to_lowercase();
            !(l == "0" || l == "false" || l == "no" || l.is_empty())
        })
        .unwrap_or(default)
}

/// Kind (request) → bit in `types_mask` of offer.
fn kind_to_bit(kind: u8) -> u32 {
    match kind {
        0 => 1, // package
        1 => 2, // passenger
        _ => 0,
    }
}

/// Haversine distance in KM between two geo points (micro-degrees).
fn haversine_km(lat1_e6: i32, lon1_e6: i32, lat2_e6: i32, lon2_e6: i32) -> f64 {
    let to_rad = |x: i32| (x as f64 / 1_000_000.0) * std::f64::consts::PI / 180.0;

    let lat1 = to_rad(lat1_e6);
    let lon1 = to_rad(lon1_e6);
    let lat2 = to_rad(lat2_e6);
    let lon2 = to_rad(lon2_e6);

    let dlat = lat2 - lat1;
    let dlon = lon2 - lon1;
    let a = (dlat / 2.0).sin().powi(2)
        + lat1.cos() * lat2.cos() * (dlon / 2.0).sin().powi(2);
    let c = 2.0 * a.sqrt().atan2((1.0 - a).sqrt());
    6371.0 * c
}

/// Time-interval overlap check, as in the Python version.
fn intervals_overlap_ms(
    a_start: u64,
    a_end: u64,
    b_start: u64,
    b_end: u64,
    min_olap_ms: i64,
    early_slack_ms: i64,
    late_slack_ms: i64,
    require_overlap: bool,
) -> bool {
    // If any bound is missing/zero and overlap is required → treat as "no guarantee".
    if a_start == 0 || a_end == 0 || b_start == 0 || b_end == 0 {
        return !require_overlap;
    }

    let a_s = a_start as i64;
    let a_e = a_end as i64;
    let b_s = b_start as i64 - early_slack_ms;
    let b_e = b_end as i64 + late_slack_ms;

    let overlap = std::cmp::min(a_e, b_e) - std::cmp::max(a_s, b_s);
    overlap >= std::cmp::max(0, min_olap_ms)
}

// ------------------------- Core matching logic -------------------------

/// Compute assignment for given market (requests + offers) using a branch-and-bound
/// search with the same cost/score model as in the Python version.
fn compute_matches_for_market(
    slot: u64,
    requests: &[MarketRequest],
    offers: &[MarketOffer],
) -> (i64, Vec<MatchItem>) {
    let n = requests.len();
    let m = offers.len();

    if n == 0 || m == 0 {
        log::info!(
            "build_proposal(local): slot={} no market (n_requests={}, n_offers={})",
            slot,
            n,
            m
        );
        return (0, Vec::new());
    }

    // ---------------- Scoring parameters ----------------
    let base_score: i64 = env_i64("POBA_BASE_SCORE", 1_000_000);
    let alpha_per_km: f64 = env_f64("POBA_ALPHA_PER_KM", 1000.0);
    let beta_per_cent: f64 = env_f64("POBA_BETA_PER_CENT", 1.0);
    let skip_cost: i64 = env_i64("POBA_SKIP_COST", 100_000_000);

    let max_start_km_env: f64 = env_f64("POBA_MAX_START_KM", 0.0);
    let max_end_km_env: f64 = env_f64("POBA_MAX_END_KM", 0.0);
    let max_total_km_env: f64 = env_f64("POBA_MAX_TOTAL_KM", 0.0);

    let max_start_km = if max_start_km_env > 0.0 {
        Some(max_start_km_env)
    } else {
        None
    };
    let max_end_km = if max_end_km_env > 0.0 {
        Some(max_end_km_env)
    } else {
        None
    };
    let max_total_km = if max_total_km_env > 0.0 {
        Some(max_total_km_env)
    } else {
        None
    };

    // ---------------- Time-overlap requirements ----------------
    let require_time_overlap = env_bool("POBA_REQUIRE_TIME_OVERLAP", true);
    let min_overlap_ms: i64 = (env_f64("POBA_MIN_OVERLAP_SEC", 0.0) * 1000.0) as i64;
    let early_slack_ms: i64 = (env_f64("POBA_EARLY_SLACK_SEC", 0.0) * 1000.0) as i64;
    let late_slack_ms: i64 = (env_f64("POBA_LATE_SLACK_SEC", 0.0) * 1000.0) as i64;

    // ---------------- Debug counters ----------------
    #[derive(Debug)]
    struct DebugCounts {
        total_pairs: i64,
        filtered_by_type: i64,
        filtered_by_price: i64,
        filtered_by_time: i64,
        filtered_by_distance: i64,
        feasible_pairs: i64,
    }

    let mut debug = DebugCounts {
        total_pairs: 0,
        filtered_by_type: 0,
        filtered_by_price: 0,
        filtered_by_time: 0,
        filtered_by_distance: 0,
        feasible_pairs: 0,
    };

    // ---------------- Precompute pair cost/score ----------------
    let inf: i64 = 10_i64.pow(12);
    let mut cost: Vec<Vec<i64>> = vec![vec![inf; m]; n];
    let mut partial_score: Vec<Vec<i64>> = vec![vec![0; m]; n];
    let mut price_agreed: Vec<Vec<i64>> = vec![vec![0; m]; n];

    for (i, r) in requests.iter().enumerate() {
        let r_bit = kind_to_bit(r.kind);

        for (j, o) in offers.iter().enumerate() {
            debug.total_pairs += 1;

            // 0) Type feasibility (kind vs types_mask)
            if r_bit != 0 && (o.types_mask & r_bit) == 0 {
                debug.filtered_by_type += 1;
                continue;
            }

            // 1) Price feasibility
            let req_max_cents = r.max_price_cents as i64;
            let off_min_cents = o.min_price_cents as i64;

            if req_max_cents > 0 && off_min_cents > req_max_cents {
                debug.filtered_by_price += 1;
                continue;
            }

            // 2) Time-window feasibility
            if require_time_overlap {
                if !intervals_overlap_ms(
                    r.window_start,
                    r.window_end,
                    o.window_start,
                    o.window_end,
                    min_overlap_ms,
                    early_slack_ms,
                    late_slack_ms,
                    require_time_overlap,
                ) {
                    debug.filtered_by_time += 1;
                    continue;
                }
            }

            // 3) Distance feasibility
            let r_fl = r.from_lat;
            let r_fn = r.from_lon;
            let r_tl = r.to_lat;
            let r_tn = r.to_lon;
            let o_fl = o.from_lat;
            let o_fn = o.from_lon;
            let o_tl = o.to_lat;
            let o_tn = o.to_lon;

            let (d_start, d_end) = if r_fl == 0
                || r_fn == 0
                || r_tl == 0
                || r_tn == 0
                || o_fl == 0
                || o_fn == 0
                || o_tl == 0
                || o_tn == 0
            {
                // If caps exist and coords missing → drop, otherwise treat as 0.
                if max_start_km.is_some() || max_end_km.is_some() || max_total_km.is_some() {
                    debug.filtered_by_distance += 1;
                    continue;
                }
                (0.0, 0.0)
            } else {
                (
                    haversine_km(r_fl, r_fn, o_fl, o_fn),
                    haversine_km(r_tl, r_tn, o_tl, o_tn),
                )
            };

            let d_total = d_start + d_end;

            if let Some(cap) = max_start_km {
                if d_start > cap {
                    debug.filtered_by_distance += 1;
                    continue;
                }
            }
            if let Some(cap) = max_end_km {
                if d_end > cap {
                    debug.filtered_by_distance += 1;
                    continue;
                }
            }
            if let Some(cap) = max_total_km {
                if d_total > cap {
                    debug.filtered_by_distance += 1;
                    continue;
                }
            }

            // 4) Agreed price policy (midpoint or min_price)
            let agreed_cents = if req_max_cents > 0 {
                (off_min_cents + req_max_cents) / 2
            } else {
                off_min_cents
            };
            let p_cents = std::cmp::max(1, agreed_cents);

            // 5) Scoring / penalty
            let penalty =
                (alpha_per_km * d_total + beta_per_cent * p_cents as f64).round() as i64;
            let score = std::cmp::max(0, base_score - penalty);

            cost[i][j] = penalty;
            partial_score[i][j] = score;
            price_agreed[i][j] = p_cents;
            debug.feasible_pairs += 1;
        }
    }

    // ---------------- Branch & Bound search (IDA*-like) ----------------
    //
    // state: index i (request index), used_mask (offers already taken), acc_cost.
    // Only the cheapest combination (with skip_cost) is kept.

    let mut best_cost: i64 = inf;
    let mut best_assign: Vec<Option<usize>> = vec![None; n];
    let mut current_assign: Vec<Option<usize>> = vec![None; n];

    fn dfs(
        i: usize,
        used_mask: u64,
        acc_cost: i64,
        n: usize,
        m: usize,
        cost: &Vec<Vec<i64>>,
        skip_cost: i64,
        inf: i64,
        best_cost: &mut i64,
        current_assign: &mut Vec<Option<usize>>,
        best_assign: &mut Vec<Option<usize>>,
    ) {
        if i == n {
            if acc_cost < *best_cost {
                *best_cost = acc_cost;
                *best_assign = current_assign.clone();
            }
            return;
        }

        if acc_cost >= *best_cost {
            // Already worse than best known solution
            return;
        }

        // 1) Try real matches first (prefer them over skip when possible)
        for j in 0..m {
            if ((used_mask >> j) & 1) == 1 {
                continue;
            }
            let c_ij = cost[i][j];
            if c_ij >= inf {
                continue;
            }
            let new_cost = acc_cost + c_ij;
            if new_cost >= *best_cost {
                continue;
            }

            current_assign[i] = Some(j);
            dfs(
                i + 1,
                used_mask | (1 << j),
                new_cost,
                n,
                m,
                cost,
                skip_cost,
                inf,
                best_cost,
                current_assign,
                best_assign,
            );
            current_assign[i] = None;
        }

        // 2) Option to skip this request
        let new_cost = acc_cost + skip_cost;
        if new_cost < *best_cost {
            current_assign[i] = None;
            dfs(
                i + 1,
                used_mask,
                new_cost,
                n,
                m,
                cost,
                skip_cost,
                inf,
                best_cost,
                current_assign,
                best_assign,
            );
        }
    }

    dfs(
        0,
        0,
        0,
        n,
        m,
        &cost,
        skip_cost,
        inf,
        &mut best_cost,
        &mut current_assign,
        &mut best_assign,
    );

    if best_cost >= inf {
        log::info!(
            "build_proposal(local): slot={} no feasible assignment debug={:?}",
            slot,
            debug
        );
        return (0, Vec::new());
    }

    // ---------------- Rebuild matches + total_score ----------------
    let mut matches: Vec<MatchItem> = Vec::new();
    let mut total_score: i64 = 0;

    for i in 0..n {
        if let Some(j) = best_assign[i] {
            let r = &requests[i];
            let o = &offers[j];

            let agreed_cents = price_agreed[i][j];
            let sc = partial_score[i][j];

            matches.push(MatchItem {
                request_uuid: r.uuid_16.clone(),
                offer_uuid: o.uuid_16.clone(),
                agreed_price_cents: agreed_cents as u32,
                partial_score: sc,
            });

            total_score += sc;
        }
    }

    log::info!(
        "build_proposal(local): slot={} total_score={} matches={} \
         (skip_cost={}, require_time_overlap={}, min_overlap_ms={}, \
         early_slack_ms={}, late_slack_ms={}, debug={:?})",
        slot,
        total_score,
        matches.len(),
        skip_cost,
        require_time_overlap,
        min_overlap_ms,
        early_slack_ms,
        late_slack_ms,
        debug,
    );

    (total_score, matches)
}

// ------------------------------ Worker loop ------------------------------

pub async fn run(
    client: Arc<FullClient>,
    // Currently not using the transaction pool, but we keep the parameter for future use.
    _tx_pool: Arc<dyn Send + Sync>,
    // Currently not using the keystore, but we keep the parameter for future use.
    _keystore: impl Send + Sync + 'static,
    backend_url: String,
) {
    let http = Http::new();

    // ROLE: proposer / finalizer
    let role = std::env::var("POBA_ROLE").unwrap_or_else(|_| "proposer".to_string());
    let is_finalizer = role.eq_ignore_ascii_case("finalizer");

    // Unique proposer ID per node ("alice", "bob", ...)
    let proposer_id =
        std::env::var("POBA_PROPOSER_ID").unwrap_or_else(|_| "node".to_string());

    log::info!(
        "PoBA worker started with role={} proposer_id={} backend_url={}",
        role,
        proposer_id,
        backend_url
    );

    // Last slot we attempted to finalize (to avoid hammering the same slot)
    let mut last_finalized_slot_local: u64 = 0;

    loop {
        // 1) Pull open market from backend
        let req_url = format!("{}/poba/requests-open", backend_url);
        let off_url = format!("{}/poba/offers-active", backend_url);

        let (requests, offers): (Vec<MarketRequest>, Vec<MarketOffer>) = match (
            http.get(&req_url).send().await,
            http.get(&off_url).send().await,
        ) {
            (Ok(r1), Ok(r2)) => {
                let rs: Vec<MarketRequest> = r1.json().await.unwrap_or_default();
                let os: Vec<MarketOffer> = r2.json().await.unwrap_or_default();
                (rs, os)
            }
            _ => {
                log::warn!("PoBA worker: backend not reachable at {}", backend_url);
                tokio::time::sleep(Duration::from_secs(3)).await;
                continue;
            }
        };

        if requests.is_empty() || offers.is_empty() {
            // No market – nothing to match
            tokio::time::sleep(Duration::from_secs(3)).await;
            continue;
        }

        // 2) Compute slot from chain and run local assignment (IDA*-like)
        let slot = current_slot_from_client(&client);
        log::info!(
            "PoBA worker (role={}, proposer_id={}): using slot {} (from best block number)",
            role,
            proposer_id,
            slot
        );

        let (total_score, matches) =
            compute_matches_for_market(slot, &requests, &offers);

        if matches.is_empty() {
            log::info!(
                "PoBA worker (role={}, proposer_id={}): no matches for slot {}, skipping submit",
                role,
                proposer_id,
                slot
            );
        } else {
            // 3) Ask backend to submit signed extrinsic (submit_proposal)
            let submit_url_base = format!("{}/poba/submit-proposal", backend_url);
            let submit_url = with_proposer_id(&submit_url_base, &proposer_id);

            let body = SubmitProposalBody {
                slot,
                total_score,
                matches: matches.clone(),
            };

            match http.post(&submit_url).json(&body).send().await {
                Ok(r) => {
                    let status = r.status();
                    if !status.is_success() {
                        let txt = r.text().await.unwrap_or_default();
                        log::warn!(
                            "PoBA worker (proposer_id={}): submit-proposal HTTP status={} body={}",
                            proposer_id,
                            status,
                            txt
                        );
                    } else {
                        log::info!(
                            "PoBA worker (role={}, proposer_id={}): submit-proposal HTTP {} for slot {}",
                            role,
                            proposer_id,
                            status,
                            slot
                        );
                    }
                }
                Err(e) => {
                    log::warn!(
                        "PoBA worker (proposer_id={}): submit-proposal HTTP failed: {e}",
                        proposer_id
                    );
                }
            }
        }

        // 4) Optionally ask backend to finalize a slot
        //
        // We allow configuring how many slots "behind" we finalize:
        //   POBA_FINALIZE_LAG_SLOTS = 0  (default)  → finalize *current* slot
        //   POBA_FINALIZE_LAG_SLOTS = 1            → finalize slot-1
        if is_finalizer {
            let lag_slots: u64 = std::env::var("POBA_FINALIZE_LAG_SLOTS")
                .ok()
                .and_then(|v| v.parse::<u64>().ok())
                .unwrap_or(0); // 👈 default: current slot

            let finalize_slot = slot.saturating_sub(lag_slots);

            if finalize_slot > 0 && finalize_slot > last_finalized_slot_local {
                let finalize_url_base = format!("{}/poba/finalize-slot", backend_url);
                let finalize_url = with_proposer_id(&finalize_url_base, &proposer_id);

                log::info!(
                    "PoBA worker (finalizer, proposer_id={}): attempting finalize-slot for slot {} (current_slot={}, lag={})",
                    proposer_id,
                    finalize_slot,
                    slot,
                    lag_slots,
                );

                match http
                    .post(&finalize_url)
                    .json(&serde_json::json!({ "slot": finalize_slot }))
                    .send()
                    .await
                {
                    Ok(resp) => {
                        let status = resp.status();
                        let body_txt = resp.text().await.unwrap_or_default();
                        if status.is_success() {
                            log::info!(
                                "PoBA worker (finalizer, proposer_id={}): finalize-slot OK for slot {} (status={}, body={})",
                                proposer_id,
                                finalize_slot,
                                status,
                                body_txt
                            );
                        } else {
                            log::warn!(
                                "PoBA worker (finalizer, proposer_id={}): finalize-slot HTTP {} for slot {} body={}",
                                proposer_id,
                                status,
                                finalize_slot,
                                body_txt
                            );
                        }
                        last_finalized_slot_local = finalize_slot;
                    }
                    Err(e) => {
                        log::warn!(
                            "PoBA worker (finalizer, proposer_id={}): finalize-slot request failed for slot {}: {e}",
                            proposer_id,
                            finalize_slot
                        );
                        // We do NOT update last_finalized_slot_local, so we can retry on next loop.
                    }
                }
            } else {
                log::debug!(
                    "PoBA worker (finalizer, proposer_id={}): no finalize action (slot={}, finalize_slot={}, last_finalized_local={}, lag={})",
                    proposer_id,
                    slot,
                    finalize_slot,
                    last_finalized_slot_local,
                    lag_slots,
                );
            }
        } else {
            log::debug!(
                "PoBA worker (role={}, proposer_id={}): not a finalizer → skipping finalize-slot",
                role,
                proposer_id
            );
        }

        // Sleep for ~half a slot (block time ~6s → 3s here).
        tokio::time::sleep(Duration::from_secs(3)).await;
    }
}
