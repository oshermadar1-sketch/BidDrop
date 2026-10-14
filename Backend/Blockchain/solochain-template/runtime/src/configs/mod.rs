// This is free and unencumbered software released into the public domain.

use frame_support::{
    derive_impl, parameter_types,
    traits::{ConstBool, ConstU32, ConstU64, ConstU8},
    weights::{
        constants::{RocksDbWeight, WEIGHT_REF_TIME_PER_SECOND},
        IdentityFee, Weight,
    },
};
use frame_system::limits::{BlockLength, BlockWeights};
use pallet_transaction_payment::{ConstFeeMultiplier, FungibleAdapter, Multiplier};
use sp_consensus_aura::sr25519::AuthorityId as AuraId;
use sp_runtime::{traits::One, Perbill};
use sp_version::RuntimeVersion;

// Pull runtime items from the parent module (runtime/src/lib.rs)
use crate::{
    AccountId, Balance, Block, BlockNumber, Hash, Nonce, VERSION, SLOT_DURATION, EXISTENTIAL_DEPOSIT,
    Aura, Balances, Runtime, RuntimeCall, RuntimeEvent, System, PalletInfo, RuntimeOrigin,
};

const NORMAL_DISPATCH_RATIO: Perbill = Perbill::from_percent(75);

parameter_types! {
    // Keep 2400 recent block hashes (used by light clients, forks, etc.)
    pub const BlockHashCount: BlockNumber = 2400;
    pub const Version: RuntimeVersion = VERSION;

    /// We allow for ~2 seconds of compute with a 6 second average block time.
    /// Tune as needed; this does not change the *slot* length.
    pub RuntimeBlockWeights: BlockWeights = BlockWeights::with_sensible_defaults(
        Weight::from_parts(2u64 * WEIGHT_REF_TIME_PER_SECOND, u64::MAX),
        NORMAL_DISPATCH_RATIO,
    );

    /// Max block length ~5MB, with 75% for normal extrinsics.
    pub RuntimeBlockLength: BlockLength =
        BlockLength::max_with_normal_ratio(5 * 1024 * 1024, NORMAL_DISPATCH_RATIO);

    // SS58 address prefix (42 = generic Substrate)
    pub const SS58Prefix: u16 = 42;
}

/// The default types are injected by `derive_impl` from
/// `frame_system::config_preludes::SolochainDefaultConfig`, overridden as needed.
#[derive_impl(frame_system::config_preludes::SolochainDefaultConfig)]
impl frame_system::Config for Runtime {
    type Block = Block;
    type BlockWeights = RuntimeBlockWeights;
    type BlockLength = RuntimeBlockLength;

    type AccountId = AccountId;
    type Nonce = Nonce;
    type Hash = Hash;
    type BlockHashCount = BlockHashCount;
    type DbWeight = RocksDbWeight;
    type Version = Version;

    type AccountData = pallet_balances::AccountData<Balance>;
    type SS58Prefix = SS58Prefix;
    type MaxConsumers = frame_support::traits::ConstU32<16>;

    // Required by the derive; created by construct_runtime!
    type RuntimeOrigin = RuntimeOrigin;

    // Added to satisfy errors E0412:
    type RuntimeTask = ();         // no background tasks in this minimal runtime
    type PalletInfo = PalletInfo;  // provided by construct_runtime!
}

/// Aura config:
/// - `SlotDuration` is derived from Timestamp's MinimumPeriod * 2.
/// - We keep one author per slot.
impl pallet_aura::Config for Runtime {
    type AuthorityId = AuraId;
    type DisabledValidators = ();
    type MaxAuthorities = ConstU32<32>;
    type AllowMultipleBlocksPerSlot = ConstBool<false>;
    type SlotDuration = pallet_aura::MinimumPeriodTimesTwo<Runtime>;
}

/// Grandpa finality (minimal for a dev/solo chain).
impl pallet_grandpa::Config for Runtime {
    type RuntimeEvent = RuntimeEvent;
    type WeightInfo = ();
    type MaxAuthorities = ConstU32<32>;
    type MaxNominators = ConstU32<0>;
    type MaxSetIdSessionEntries = ConstU64<0>;
    type KeyOwnerProof = sp_core::Void;
    type EquivocationReportSystem = ();
}

/// Timestamp config:
/// - **IMPORTANT**: `MinimumPeriod = SLOT_DURATION / 2`.
///   With `SLOT_DURATION = 6000` (in lib.rs), MinimumPeriod = 3000ms,
///   so Aura slot = 3000*2 = **6000ms**.
impl pallet_timestamp::Config for Runtime {
    type Moment = u64;
    type OnTimestampSet = Aura;
    type MinimumPeriod = ConstU64<{ SLOT_DURATION / 2 }>;
    type WeightInfo = ();
}

/// Balances config (basic).
/// NOTE: We do **not** use Freeze/Hold reasons in this runtime to keep things simple.
///       If you later add `RuntimeHoldReason`/`RuntimeFreezeReason` derives in the runtime macro,
///       you can re-enable the related associated types here.
impl pallet_balances::Config for Runtime {
    type MaxLocks = ConstU32<50>;
    type MaxReserves = ();
    type ReserveIdentifier = [u8; 8];

    type Balance = Balance;
    type RuntimeEvent = RuntimeEvent;
    type DustRemoval = ();
    type ExistentialDeposit = frame_support::traits::ConstU128<{ EXISTENTIAL_DEPOSIT }>;
    type AccountStore = System;

    type WeightInfo = pallet_balances::weights::SubstrateWeight<Runtime>;

    // No freeze/hold reasons in this minimal setup:
    type FreezeIdentifier = ();
    type MaxFreezes = ();
    type RuntimeHoldReason = ();
    type RuntimeFreezeReason = ();
    type DoneSlashHandler = ();
}

parameter_types! {
    pub FeeMultiplier: Multiplier = Multiplier::one();
}

/// Transaction payment config (simple linear fees; easy to tweak later).
impl pallet_transaction_payment::Config for Runtime {
    type RuntimeEvent = RuntimeEvent;
    type OnChargeTransaction = FungibleAdapter<Balances, ()>;
    type OperationalFeeMultiplier = ConstU8<5>;
    type WeightToFee = IdentityFee<Balance>;
    type LengthToFee = IdentityFee<Balance>;
    type FeeMultiplierUpdate = ConstFeeMultiplier<FeeMultiplier>;
    type WeightInfo = pallet_transaction_payment::weights::SubstrateWeight<Runtime>;
}

/// Sudo (for dev/admin operations).
impl pallet_sudo::Config for Runtime {
    type RuntimeEvent = RuntimeEvent;
    type RuntimeCall = RuntimeCall;
    type WeightInfo = pallet_sudo::weights::SubstrateWeight<Runtime>;
}

/// Example template pallet (optional).
impl pallet_template::Config for Runtime {
    type RuntimeEvent = RuntimeEvent;
    type WeightInfo = pallet_template::weights::SubstrateWeight<Runtime>;
}