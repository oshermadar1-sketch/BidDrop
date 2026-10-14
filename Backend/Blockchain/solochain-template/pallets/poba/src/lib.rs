#![cfg_attr(not(feature = "std"), no_std)]

// --------------------------- Imports & Prelude ---------------------------
use codec::{Decode, Encode, MaxEncodedLen};
use frame_support::{pallet_prelude::*, BoundedVec};
use frame_system::pallet_prelude::*;
use scale_info::TypeInfo;
use sp_runtime::RuntimeDebug;
use sp_std::vec::Vec;

// --------------------------- Domain Types ---------------------------

/// A single matched pair (request ↔ offer) with a score contribution.
#[derive(Clone, PartialEq, Eq, Encode, Decode, MaxEncodedLen, TypeInfo, RuntimeDebug)]
pub struct Match {
    pub request_uuid: [u8; 16],
    pub offer_uuid:   [u8; 16],
    pub agreed_price_cents: u32,
    pub partial_score: i64,
}

/// Upper bound on how many matches a single proposal may include.
pub const MAX_MATCHES_PER_PROPOSAL: u32 = 256;
pub type MatchesBounded = BoundedVec<Match, ConstU32<MAX_MATCHES_PER_PROPOSAL>>;

/// A full proposal as stored on-chain for a given slot.
#[derive(Clone, PartialEq, Eq, Encode, Decode, MaxEncodedLen, TypeInfo, RuntimeDebug)]
pub struct Proposal {
    pub total_score: i64,
    pub matches:     MatchesBounded,
}

// ------------------------------ Pallet ------------------------------

#[frame_support::pallet]
pub mod pallet {
    use super::*;

    // -------- Config --------
    #[pallet::config]
    pub trait Config: frame_system::Config {
        /// Pallet events.
        type RuntimeEvent: From<Event<Self>> + IsType<<Self as frame_system::Config>::RuntimeEvent>;
    }

    /// The pallet type.
    #[pallet::pallet]
    pub struct Pallet<T>(_);

    // -------- Storage --------

    /// For each slot, keep the *best* proposal seen so far (by total_score).
    #[pallet::storage]
    #[pallet::getter(fn best_proposal)]
    pub type BestProposal<T: Config> =
        StorageMap<_, Blake2_128Concat, u64 /*slot*/, Proposal, OptionQuery>;

    /// Final winner per slot after `finalize_slot`.
    #[pallet::storage]
    #[pallet::getter(fn finalized_proposal)]
    pub type FinalizedProposal<T: Config> =
        StorageMap<_, Blake2_128Concat, u64 /*slot*/, Proposal, OptionQuery>;

    /// The last finalized slot (for convenience from UI/backend).
    #[pallet::storage]
    #[pallet::getter(fn last_finalized_slot)]
    pub type LastFinalizedSlot<T: Config> = StorageValue<_, u64, ValueQuery>;

    // -------- Events --------

    #[pallet::event]
    #[pallet::generate_deposit(pub(super) fn deposit_event)]
    pub enum Event<T: Config> {
        /// A proposal was submitted for `slot` with `total_score` and `matches` count,
        /// including the account that submitted it.
        ProposalSubmitted {
            slot: u64,
            total_score: i64,
            matches: u32,
            proposer: T::AccountId,
        },
        /// The slot was finalized with the winning `total_score` and `matches` count.
        SlotFinalized     {
            slot: u64,
            total_score: i64,
            matches: u32,
        },
    }

    // -------- Errors --------

    #[pallet::error]
    pub enum Error<T> {
        /// Submitted proposal has more matches than allowed by the bound.
        TooManyMatches,
        /// No proposal exists for the given slot (or proposal has empty matches).
        NoProposalForSlot,
        /// Submitted proposal has zero matches (not allowed).
        EmptyMatches,
    }

    // -------- Calls --------

    #[pallet::call]
    impl<T: Config> Pallet<T> {
        /// Submit (or improve) the best proposal for a given slot.
        ///
        /// NOTE: To satisfy FRAME's DecodeWithMemTracking on call parameters,
        /// we accept Vec of tuples and convert inside.
        #[pallet::weight(10_000)]
        pub fn submit_proposal(
            origin: OriginFor<T>,
            slot: u64,
            total_score: i64,
            // (request_uuid, offer_uuid, agreed_price_cents, partial_score)
            matches: Vec<([u8; 16], [u8; 16], u32, i64)>,
        ) -> DispatchResult {
            // מי הגיש את ההצעה (Alice / Bob וכו')
            let who = ensure_signed(origin)?;

            // Convert tuples → Match → BoundedVec
            let mut tmp: Vec<Match> = Vec::with_capacity(matches.len());
            for (rq, of, price, part) in matches.into_iter() {
                tmp.push(Match {
                    request_uuid: rq,
                    offer_uuid: of,
                    agreed_price_cents: price,
                    partial_score: part,
                });
            }
            let bounded: MatchesBounded =
                BoundedVec::try_from(tmp).map_err(|_| Error::<T>::TooManyMatches)?;

            // Reject empty proposals
            ensure!(!bounded.is_empty(), Error::<T>::EmptyMatches);

            let matches_len: u32 = bounded.len() as u32;
            let proposal = Proposal {
                total_score,
                matches: bounded,
            };

            // לעדכן BestProposal רק אם זו ההצעה הראשונה לסלוט
            // או אם היא משפרת את total_score, אבל:
            // *תמיד* נייצר אירוע ProposalSubmitted (גם אם לא שיפרנו).
            match BestProposal::<T>::get(slot) {
                Some(existing) => {
                    if total_score > existing.total_score {
                        BestProposal::<T>::insert(slot, &proposal);
                    }
                }
                None => {
                    BestProposal::<T>::insert(slot, &proposal);
                }
            }

            // 🔔 אירוע תמידי – כל הגשה נרשמת, כולל מי הגיש
            Self::deposit_event(Event::ProposalSubmitted {
                slot,
                total_score,
                matches: matches_len,
                proposer: who,
            });

            Ok(())
        }

        /// Finalize a slot: move best → finalized, update last slot, emit rich event.
        #[pallet::weight(10_000)]
        pub fn finalize_slot(origin: OriginFor<T>, slot: u64) -> DispatchResult {
            let _who = ensure_signed(origin)?;

            // Must have a non-empty best proposal for this slot
            let winner = BestProposal::<T>::take(slot).ok_or(Error::<T>::NoProposalForSlot)?;
            ensure!(!winner.matches.is_empty(), Error::<T>::NoProposalForSlot);

            let matches_len = winner.matches.len() as u32;

            FinalizedProposal::<T>::insert(slot, &winner);
            LastFinalizedSlot::<T>::put(slot);

            Self::deposit_event(Event::SlotFinalized {
                slot,
                total_score: winner.total_score,
                matches: matches_len,
            });

            Ok(())
        }
    }
}

// Re-export for `impl pallet_poba::Config for Runtime`
pub use pallet::*;
