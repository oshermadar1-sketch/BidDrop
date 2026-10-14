#![cfg_attr(not(feature = "std"), no_std)]

// Basic imports
use codec::{Decode, Encode, MaxEncodedLen};
use frame_support::pallet_prelude::*;
use frame_system::pallet_prelude::*;
use frame_system::pallet_prelude::BlockNumberFor; // ✅
use scale_info::TypeInfo;
use sp_runtime::RuntimeDebug;
use sp_runtime::traits::AtLeast32BitUnsigned;

// --------------------------- Domain Types ---------------------------

// We reuse 16-byte UUIDs like in PoBA
pub type RequestUuid = [u8; 16];
pub type OfferUuid   = [u8; 16];

// Escrow identifier on-chain (independent from DB UUID)
pub type EscrowId = u64;

/// Delivery / assignment state machine on-chain.
#[derive(Clone, PartialEq, Eq, Encode, Decode, MaxEncodedLen, TypeInfo, RuntimeDebug)]
pub enum DeliveryStatus {
    /// Assignment was created (after PoBA winner chosen, before pickup).
    Created,
    /// Courier/driver marked that the package/passenger was picked up.
    PickedUpByCourier,
    /// Courier/driver marked that delivery/arrival was completed.
    DeliveredByCourier,
    /// Receiver (or payer) confirmed the delivery/arrival.
    ConfirmedByReceiver,
    /// Payment was released automatically after timeout.
    TimeoutReleased,
    /// Assignment was cancelled (optional, not yet wired to flows).
    Cancelled,
    /// Assignment failed (optional, not yet wired to flows).
    Failed,
}

/// On-chain escrow record for a single assignment.
/// Note: this is *logical* escrow. Actual money is handled off-chain.
#[derive(Clone, PartialEq, Eq, Encode, Decode, MaxEncodedLen, TypeInfo, RuntimeDebug)]
pub struct AssignmentEscrow<AccountId, Balance, BlockNumber> {
    pub request_uuid: RequestUuid,
    pub offer_uuid:   OfferUuid,
    pub driver:       AccountId,
    pub payer:        AccountId,
    /// Monetary amount for this assignment (e.g., in cents or chain base units).
    pub amount:       Balance,
    pub status:       DeliveryStatus,
    pub created_at:   BlockNumber,
    pub deadline:     BlockNumber,
}

// ------------------------------ Pallet ------------------------------

#[frame_support::pallet]
pub mod pallet {
    use super::*;

    #[pallet::config]
    pub trait Config: frame_system::Config {
        /// Pallet events.
        type RuntimeEvent: From<Event<Self>> + IsType<<Self as frame_system::Config>::RuntimeEvent>;

        /// Balance type used for escrow amounts (e.g., Runtime's Balance).
        type Balance: Parameter + AtLeast32BitUnsigned + Default + Copy + MaxEncodedLen;

        /// How many blocks until auto-timeout -> payment release.
        ///
        /// We use BlockNumberFor<Self> which is the canonical "block number"
        /// type of the runtime (Header::Number).
        #[pallet::constant]
        type ConfirmationTimeoutBlocks: Get<BlockNumberFor<Self>>;
    }

    #[pallet::pallet]
    pub struct Pallet<T>(_);

    // -------- Storage --------

    /// Incremental counter for on-chain EscrowId.
    #[pallet::storage]
    #[pallet::getter(fn next_escrow_id)]
    pub type NextEscrowId<T: Config> = StorageValue<_, EscrowId, ValueQuery>;

    /// Main escrow storage: EscrowId -> AssignmentEscrow.
    #[pallet::storage]
    #[pallet::getter(fn escrows)]
    pub type Escrows<T: Config> = StorageMap<
        _,
        Blake2_128Concat,
        EscrowId,
        AssignmentEscrow<
            T::AccountId,
            T::Balance,
            BlockNumberFor<T> // <--- uses BlockNumberFor<T>
        >,
        OptionQuery
    >;

    /// Mapping to ensure a single active escrow per request.
    ///
    /// IMPORTANT:
    ///  - We only block multiple escrows *per request_uuid*,
    ///    not per offer, so the same driver/offer can still take
    ///    multiple assignments, but each request is matched once.
    #[pallet::storage]
    #[pallet::getter(fn request_to_escrow)]
    pub type RequestToEscrow<T: Config> =
        StorageMap<_, Blake2_128Concat, RequestUuid, EscrowId, OptionQuery>;

    // -------- Events --------

    #[pallet::event]
    #[pallet::generate_deposit(pub(super) fn deposit_event)]
    pub enum Event<T: Config> {
        /// New escrow created for (request, offer).
        EscrowCreated {
            escrow_id: EscrowId,
            request_uuid: RequestUuid,
            offer_uuid: OfferUuid,
            driver: T::AccountId,
            payer: T::AccountId,
            amount: T::Balance,
            deadline: BlockNumberFor<T>,
        },
        /// Courier marked pickup.
        PickedUp {
            escrow_id: EscrowId,
        },
        /// Courier marked delivery.
        Delivered {
            escrow_id: EscrowId,
        },
        /// Receiver confirmed delivery.
        ReceiverConfirmed {
            escrow_id: EscrowId,
        },
        /// Payment was released (either by confirm or timeout).
        PaymentReleased {
            escrow_id: EscrowId,
            amount: T::Balance,
        },
    }

    // -------- Errors --------

    #[pallet::error]
    pub enum Error<T> {
        /// Attempted to create a new escrow for a request that already has one.
        RequestAlreadyAssigned,
        /// Escrow not found for given id.
        EscrowNotFound,
        /// Escrow already in a final state; no further status changes allowed.
        EscrowAlreadyFinal,
        /// Caller is not the expected driver for this escrow.
        NotDriver,
        /// Caller is not the expected payer/receiver for this escrow.
        NotPayer,
        /// Invalid status transition (e.g., Delivered before PickedUp).
        InvalidStatusTransition,
        /// Amount must be strictly greater than zero.
        ZeroAmountNotAllowed,
        /// Too early to force timeout-based payment release.
        TimeoutNotReached,
    }

    // -------- Helpers --------

    impl<T: Config> Pallet<T> {
        /// Helper to get next EscrowId and increment the counter.
        fn next_id() -> EscrowId {
            let id = NextEscrowId::<T>::get();
            NextEscrowId::<T>::put(id.wrapping_add(1));
            id
        }

        /// Returns true if status is already final: no more transitions allowed.
        fn is_final_status(status: &DeliveryStatus) -> bool {
            matches!(
                status,
                DeliveryStatus::ConfirmedByReceiver
                    | DeliveryStatus::TimeoutReleased
                    | DeliveryStatus::Cancelled
                    | DeliveryStatus::Failed
            )
        }
    }

    // -------- Calls --------

    #[pallet::call]
    impl<T: Config> Pallet<T> {
        /// Create a new escrow entry for a given (request, offer).
        ///
        /// In practice this should be called by a trusted backend / authority
        /// right after PoBA finalize and DB assignment creation.
        ///
        /// NOTE: For now we only require a signed origin; origin-level
        /// authorization policy (which account is allowed to call) can be
        /// tightened later if needed.
        #[pallet::weight(10_000)]
        pub fn create_escrow(
            origin: OriginFor<T>,
            request_uuid: RequestUuid,
            offer_uuid:   OfferUuid,
            driver:       T::AccountId,
            payer:        T::AccountId,
            amount:       T::Balance,
        ) -> DispatchResult {
            let _who = ensure_signed(origin)?;

            // Prevent multiple active escrows for same request.
            ensure!(
                RequestToEscrow::<T>::get(&request_uuid).is_none(),
                Error::<T>::RequestAlreadyAssigned
            );

            // Protect against nonsense amount (0).
            ensure!(amount > T::Balance::from(0u32), Error::<T>::ZeroAmountNotAllowed);

            // Use runtime block number type
            let now: BlockNumberFor<T> = frame_system::Pallet::<T>::block_number();
            let deadline = now + T::ConfirmationTimeoutBlocks::get();

            let escrow_id = Self::next_id();

            let record = AssignmentEscrow::<
                T::AccountId,
                T::Balance,
                BlockNumberFor<T>,
            > {
                request_uuid,
                offer_uuid,
                driver: driver.clone(),
                payer: payer.clone(),
                amount,
                status: DeliveryStatus::Created,
                created_at: now,
                deadline,
            };

            Escrows::<T>::insert(escrow_id, record);
            RequestToEscrow::<T>::insert(request_uuid, escrow_id);

            Self::deposit_event(Event::EscrowCreated {
                escrow_id,
                request_uuid,
                offer_uuid,
                driver,
                payer,
                amount,
                deadline,
            });

            Ok(())
        }

        /// Courier marks pickup.
        #[pallet::weight(10_000)]
        pub fn mark_picked_up(
            origin: OriginFor<T>,
            escrow_id: EscrowId,
        ) -> DispatchResult {
            let who = ensure_signed(origin)?;

            Escrows::<T>::try_mutate(escrow_id, |maybe| -> DispatchResult {
                let escrow = maybe.as_mut().ok_or(Error::<T>::EscrowNotFound)?;

                // Final states cannot be modified anymore.
                ensure!(!Self::is_final_status(&escrow.status), Error::<T>::EscrowAlreadyFinal);

                // Only the recorded driver can mark pickup (can be relaxed if needed).
                ensure!(who == escrow.driver, Error::<T>::NotDriver);

                // Valid transition: Created -> PickedUpByCourier only.
                match escrow.status {
                    DeliveryStatus::Created => {
                        escrow.status = DeliveryStatus::PickedUpByCourier;
                    }
                    _ => return Err(Error::<T>::InvalidStatusTransition.into()),
                }

                Ok(())
            })?;

            Self::deposit_event(Event::PickedUp { escrow_id });
            Ok(())
        }

        /// Courier marks delivery.
        #[pallet::weight(10_000)]
        pub fn mark_delivered(
            origin: OriginFor<T>,
            escrow_id: EscrowId,
        ) -> DispatchResult {
            let who = ensure_signed(origin)?;

            Escrows::<T>::try_mutate(escrow_id, |maybe| -> DispatchResult {
                let escrow = maybe.as_mut().ok_or(Error::<T>::EscrowNotFound)?;

                ensure!(!Self::is_final_status(&escrow.status), Error::<T>::EscrowAlreadyFinal);
                ensure!(who == escrow.driver, Error::<T>::NotDriver);

                // Valid transition: PickedUpByCourier -> DeliveredByCourier.
                match escrow.status {
                    DeliveryStatus::PickedUpByCourier => {
                        escrow.status = DeliveryStatus::DeliveredByCourier;
                    }
                    _ => return Err(Error::<T>::InvalidStatusTransition.into()),
                }

                Ok(())
            })?;

            Self::deposit_event(Event::Delivered { escrow_id });
            Ok(())
        }

        /// Receiver (payer) confirms the delivery/arrival.
        ///
        /// At this point, backend should listen for `PaymentReleased` and
        /// perform capture via Stripe/credit-card provider.
        #[pallet::weight(10_000)]
        pub fn confirm_received(
            origin: OriginFor<T>,
            escrow_id: EscrowId,
        ) -> DispatchResult {
            let who = ensure_signed(origin)?;

            let mut amount_to_release: T::Balance = T::Balance::from(0u32);

            Escrows::<T>::try_mutate(escrow_id, |maybe| -> DispatchResult {
                let escrow = maybe.as_mut().ok_or(Error::<T>::EscrowNotFound)?;

                ensure!(!Self::is_final_status(&escrow.status), Error::<T>::EscrowAlreadyFinal);
                ensure!(who == escrow.payer, Error::<T>::NotPayer);

                // Valid transition: DeliveredByCourier -> ConfirmedByReceiver.
                match escrow.status {
                    DeliveryStatus::DeliveredByCourier => {
                        escrow.status = DeliveryStatus::ConfirmedByReceiver;
                    }
                    _ => return Err(Error::<T>::InvalidStatusTransition.into()),
                }

                amount_to_release = escrow.amount;

                Ok(())
            })?;

            Self::deposit_event(Event::PaymentReleased {
                escrow_id,
                amount: amount_to_release,
            });
            Self::deposit_event(Event::ReceiverConfirmed { escrow_id });

            Ok(())
        }

        /// Backend-style release based on (request_uuid, offer_uuid).
        ///
        /// This is the extrinsic that the backend calls from
        /// `_release_onchain_escrow_for_assignment`:
        ///
        ///   Escrow::release_escrow(request_uuid, offer_uuid)
        ///
        /// It:
        ///   - Locates the escrow via `RequestToEscrow`.
        ///   - Verifies the stored offer_uuid matches.
        ///   - Ensures the escrow is not in a final status.
        ///   - Sets status = ConfirmedByReceiver.
        ///   - Emits PaymentReleased + ReceiverConfirmed.
        #[pallet::weight(10_000)]
        pub fn release_escrow(
            origin: OriginFor<T>,
            request_uuid: RequestUuid,
            offer_uuid: OfferUuid,
        ) -> DispatchResult {
            let _who = ensure_signed(origin)?;

            let escrow_id =
                RequestToEscrow::<T>::get(&request_uuid).ok_or(Error::<T>::EscrowNotFound)?;

            let mut amount_to_release: T::Balance = T::Balance::from(0u32);

            Escrows::<T>::try_mutate(escrow_id, |maybe| -> DispatchResult {
                let escrow = maybe.as_mut().ok_or(Error::<T>::EscrowNotFound)?;

                // Sanity: ensure the offer matches the one we expect.
                ensure!(escrow.offer_uuid == offer_uuid, Error::<T>::EscrowNotFound);

                // Do not allow double release or further transitions from final states.
                ensure!(
                    !Self::is_final_status(&escrow.status),
                    Error::<T>::EscrowAlreadyFinal
                );

                // Mark as confirmed by receiver and prepare amount for the event.
                escrow.status = DeliveryStatus::ConfirmedByReceiver;
                amount_to_release = escrow.amount;

                Ok(())
            })?;

            Self::deposit_event(Event::PaymentReleased {
                escrow_id,
                amount: amount_to_release,
            });
            Self::deposit_event(Event::ReceiverConfirmed { escrow_id });

            Ok(())
        }

        /// Force payment release after timeout if receiver did not confirm.
        ///
        /// Can be called by anyone; the on-chain guard is purely by block number
        /// and current status.
        #[pallet::weight(10_000)]
        pub fn force_timeout_release(
            origin: OriginFor<T>,
            escrow_id: EscrowId,
        ) -> DispatchResult {
            let _who = ensure_signed(origin)?;

            let mut amount_to_release: T::Balance = T::Balance::from(0u32);
            let now: BlockNumberFor<T> = frame_system::Pallet::<T>::block_number();

            Escrows::<T>::try_mutate(escrow_id, |maybe| -> DispatchResult {
                let escrow = maybe.as_mut().ok_or(Error::<T>::EscrowNotFound)?;

                ensure!(!Self::is_final_status(&escrow.status), Error::<T>::EscrowAlreadyFinal);

                // Only allow timeout if current block >= deadline.
                ensure!(now >= escrow.deadline, Error::<T>::TimeoutNotReached);

                escrow.status = DeliveryStatus::TimeoutReleased;
                amount_to_release = escrow.amount;

                Ok(())
            })?;

            Self::deposit_event(Event::PaymentReleased {
                escrow_id,
                amount: amount_to_release,
            });

            Ok(())
        }
    }
}

// Re-export for `impl pallet_escrow::Config for Runtime`
pub use pallet::*;
