#![cfg_attr(not(feature = "std"), no_std, no_main)]

#[ink::contract]
mod escrow {
    // Bring Vec into scope for no_std environment.
    use ink::prelude::vec::Vec;
    // Bring SCALE encode/decode traits from ink's re-exported module.
    use ink::scale::{Decode, Encode};
    // Type metadata for std (used by tools/UI), only when std is enabled.
    #[cfg(feature = "std")]
    use ink::scale_info::TypeInfo;
    // Mapping for on-chain storage.
    use ink::storage::Mapping;

    /// Input for a single assignment in the winning proposal.
    /// This is used only for validation of the PoBA winner.
    ///
    /// - `request_id`: unique ID of the request/ride/package.
    /// - `driver`: blockchain account of the driver that will serve this request.
    /// - `pair_score`: score contribution of this (request, driver) pair.
    #[derive(Encode, Decode, Clone, Debug, PartialEq, Eq)]
    #[cfg_attr(feature = "std", derive(TypeInfo))]
    pub struct AssignmentInput {
        pub request_id: u128,
        pub driver: AccountId,
        pub pair_score: u128,
    }

    // -------------------------------------------------------------------------
    // Simple status codes for escrow lifecycle (stored as u8)
    // -------------------------------------------------------------------------

    const STATUS_OPEN: u8 = 0;
    const STATUS_DELIVERED: u8 = 1;
    const STATUS_COMPLETED: u8 = 2;
    const STATUS_CANCELLED: u8 = 3;
    const STATUS_REFUNDED: u8 = 4; // reserved for future use

    /// Defines the storage of your contract.
    /// This is the original minimal storage created by `cargo contract new`,
    /// extended with escrow mappings.
    #[ink(storage)]
    pub struct Escrow {
        /// Stores a single `bool` value on the storage (demo field).
        value: bool,

        /// Mapping from assignment_id (u128) to sender (payer).
        senders: Mapping<u128, AccountId>,

        /// Mapping from assignment_id (u128) to driver (payee).
        drivers: Mapping<u128, AccountId>,

        /// Mapping from assignment_id (u128) to locked amount.
        amounts: Mapping<u128, Balance>,

        /// Mapping from assignment_id (u128) to status (STATUS_* constant).
        statuses: Mapping<u128, u8>,

        /// Mapping from assignment_id (u128) to creation timestamp (ms).
        created_ats: Mapping<u128, u64>,

        /// Mapping from assignment_id (u128) to delivery timestamp (ms).
        delivered_ats: Mapping<u128, u64>,

        /// Mapping from assignment_id (u128) to timeout in ms
        /// (how long after Delivered we allow auto-release).
        timeouts_ms: Mapping<u128, u64>,
    }

    impl Escrow {
        // ---------------------------------------------------------------------
        // Constructors (unchanged interface, extended init)
        // ---------------------------------------------------------------------

        /// Constructor that initializes the `bool` value to the given `init_value`.
        /// Also initializes all escrow mappings as empty.
        #[ink(constructor)]
        pub fn new(init_value: bool) -> Self {
            Self {
                value: init_value,
                senders: Mapping::default(),
                drivers: Mapping::default(),
                amounts: Mapping::default(),
                statuses: Mapping::default(),
                created_ats: Mapping::default(),
                delivered_ats: Mapping::default(),
                timeouts_ms: Mapping::default(),
            }
        }

        /// Constructor that initializes the `bool` value to `false`.
        ///
        /// Constructors can delegate to other constructors.
        #[ink(constructor)]
        pub fn default() -> Self {
            Self::new(Default::default())
        }

        // ---------------------------------------------------------------------
        // Original demo API (flip / get) - kept for compatibility and tests
        // ---------------------------------------------------------------------

        /// A message that flips the stored `bool` from `true` to `false` or vice versa.
        #[ink(message)]
        pub fn flip(&mut self) {
            self.value = !self.value;
        }

        /// Simply returns the current value of our `bool`.
        #[ink(message)]
        pub fn get(&self) -> bool {
            self.value
        }

        // ---------------------------------------------------------------------
        // Internal helpers for escrow
        // ---------------------------------------------------------------------

        /// Returns the current block timestamp in milliseconds.
        fn now(&self) -> u64 {
            self.env().block_timestamp()
        }

        /// Helper: load all relevant escrow fields for a given assignment_id.
        ///
        /// Panics with a clear message if there is no escrow for this id.
        fn load_escrow(
            &self,
            assignment_id: u128,
        ) -> (AccountId, AccountId, Balance, u8, u64, u64) {
            let sender = self
                .senders
                .get(assignment_id)
                .expect("Escrow: sender not found (invalid assignment_id)");
            let driver = self
                .drivers
                .get(assignment_id)
                .expect("Escrow: driver not found (invalid assignment_id)");
            let amount = self
                .amounts
                .get(assignment_id)
                .expect("Escrow: amount not found (invalid assignment_id)");
            let status = self
                .statuses
                .get(assignment_id)
                .expect("Escrow: status not found (invalid assignment_id)");
            let delivered_at = self
                .delivered_ats
                .get(assignment_id)
                .unwrap_or(0);
            let timeout_ms = self
                .timeouts_ms
                .get(assignment_id)
                .unwrap_or(0);

            (sender, driver, amount, status, delivered_at, timeout_ms)
        }

        // ---------------------------------------------------------------------
        // Escrow messages (payment & timeout logic)
        // ---------------------------------------------------------------------

        /// Open an escrow for a given assignment and deposit funds.
        ///
        /// Usage from backend/frontend:
        /// - Caller must be the sender (owner of the request).
        /// - Caller transfers the full payment as `transferred_value`.
        ///
        /// Parameters:
        /// - `assignment_id`: ID from off-chain DB, mapped to u128.
        /// - `driver`: AccountId of the driver that should receive the funds.
        /// - `timeout_ms`: How long after 'Delivered' we allow auto-release
        ///                 if the receiver does not confirm (e.g. 48h in ms).
        ///
        /// Fails (panics) if:
        /// - There is already an escrow for this assignment_id.
        #[ink(message, payable)]
        pub fn open_and_deposit(
            &mut self,
            assignment_id: u128,
            driver: AccountId,
            timeout_ms: u64,
        ) {
            // Do not override an existing escrow.
            let existing_sender: Option<AccountId> = self.senders.get(assignment_id);
            assert!(
                existing_sender.is_none(),
                "Escrow already exists for this assignment_id"
            );

            let sender = self.env().caller();
            let amount = self.env().transferred_value();
            let now = self.now();

            // Store all fields in their respective mappings.
            self.senders.insert(assignment_id, &sender);
            self.drivers.insert(assignment_id, &driver);
            self.amounts.insert(assignment_id, &amount);
            self.statuses.insert(assignment_id, &STATUS_OPEN);
            self.created_ats.insert(assignment_id, &now);
            self.delivered_ats.insert(assignment_id, &0);
            self.timeouts_ms.insert(assignment_id, &timeout_ms);
        }

        /// Driver marks the assignment as delivered / completed.
        ///
        /// Only the configured driver can call this function.
        /// Requirements:
        /// - Escrow must exist.
        /// - Escrow status must be Open.
        ///
        /// Effects:
        /// - Status moves from Open -> Delivered.
        /// - delivered_at is set to current timestamp.
        #[ink(message)]
        pub fn driver_mark_delivered(&mut self, assignment_id: u128) {
            let caller = self.env().caller();

            let (_sender, driver, _amount, status, _delivered_at, _timeout_ms) =
                self.load_escrow(assignment_id);

            assert!(
                caller == driver,
                "Only the driver can mark this escrow as delivered"
            );
            assert!(
                status == STATUS_OPEN,
                "Escrow must be in OPEN status to mark delivered"
            );

            let now = self.now();
            self.statuses.insert(assignment_id, &STATUS_DELIVERED);
            self.delivered_ats.insert(assignment_id, &now);
        }

        /// Receiver (sender in this model) confirms that the delivery/ride is OK.
        ///
        /// Only the original sender can call this method.
        /// Requirements:
        /// - Escrow must exist.
        /// - Escrow status must be Delivered.
        ///
        /// Effects:
        /// - Transfers funds from the contract to the driver.
        /// - Status moves to Completed.
        #[ink(message)]
        pub fn receiver_confirm(&mut self, assignment_id: u128) {
            let caller = self.env().caller();

            let (sender, driver, amount, status, _delivered_at, _timeout_ms) =
                self.load_escrow(assignment_id);

            assert!(
                caller == sender,
                "Only the sender (payer) can confirm the delivery"
            );
            assert!(
                status == STATUS_DELIVERED,
                "Escrow must be in DELIVERED status to confirm"
            );

            // Transfer funds to the driver.
            let transfer_result = self.env().transfer(driver, amount);
            assert!(transfer_result.is_ok(), "Transfer to driver failed");

            self.statuses.insert(assignment_id, &STATUS_COMPLETED);
        }

        /// Auto-release function for timeout handling.
        ///
        /// Anyone can call this AFTER timeout_ms has passed since 'Delivered'.
        /// Requirements:
        /// - Escrow must exist.
        /// - Status must be Delivered.
        /// - now >= delivered_at + timeout_ms.
        ///
        /// Effects:
        /// - Transfers funds to the driver.
        /// - Status moves to Completed.
        #[ink(message)]
        pub fn auto_release_if_timeout(&mut self, assignment_id: u128) {
            let (_sender, driver, amount, status, delivered_at, timeout_ms) =
                self.load_escrow(assignment_id);

            assert!(
                status == STATUS_DELIVERED,
                "Escrow must be in DELIVERED status for auto-release"
            );
            assert!(delivered_at > 0, "Delivered_at must be set");

            let now = self.now();
            let deadline = delivered_at.saturating_add(timeout_ms);
            assert!(
                now >= deadline,
                "Too early for auto-release, timeout not reached yet"
            );

            let transfer_result = self.env().transfer(driver, amount);
            assert!(transfer_result.is_ok(), "Transfer to driver failed");

            self.statuses.insert(assignment_id, &STATUS_COMPLETED);
        }

        /// Sender cancels the assignment before the driver marks it as delivered.
        ///
        /// Only the sender can call this.
        /// Allowed only when:
        /// - Status == Open.
        ///
        /// Effects:
        /// - Refunds funds back to the sender.
        /// - Status moves to Cancelled.
        #[ink(message)]
        pub fn cancel_before_delivered(&mut self, assignment_id: u128) {
            let caller = self.env().caller();

            let (sender, _driver, amount, status, _delivered_at, _timeout_ms) =
                self.load_escrow(assignment_id);

            assert!(
                caller == sender,
                "Only the sender (payer) can cancel this escrow"
            );
            assert!(
                status == STATUS_OPEN,
                "Escrow must be in OPEN status to cancel"
            );

            let transfer_result = self.env().transfer(sender, amount);
            assert!(transfer_result.is_ok(), "Refund to sender failed");

            self.statuses.insert(assignment_id, &STATUS_CANCELLED);
        }

        /// Read-only helper to inspect the status of an escrow as a raw u8.
        ///
        /// Returns:
        /// - `Some(STATUS_*)` if an escrow exists for this assignment_id.
        /// - `None` if no escrow exists.
        #[ink(message)]
        pub fn get_status(&self, assignment_id: u128) -> Option<u8> {
            self.statuses.get(assignment_id)
        }

        // ---------------------------------------------------------------------
        // PoBA winner validation API (no storage changes, pure logic)
        // ---------------------------------------------------------------------

        /// Validate the winning proposal of PoBA.
        ///
        /// This function checks TWO things:
        ///
        /// 1) Each `request_id` appears at most once in the winning assignments.
        ///    - A driver is allowed to appear multiple times (can take multiple requests).
        ///    - But the same request must not be assigned twice in this proposal.
        ///
        /// 2) The provided `winner_total_score` equals the sum of all `pair_score`
        ///    values in the `assignments` vector.
        ///
        /// Returns:
        /// - `true`  if both checks pass.
        /// - `false` if there is a duplicate request_id OR the total score does not match.
        ///
        /// NOTE:
        /// - This function does NOT change storage.
        /// - It is intended to be called from the PoBA pallet (or backend) right
        ///   before finalizing the slot. If it returns `false`, the pallet should
        ///   abort `finalize_slot` and NOT write a `FinalizedProposal` to storage.
        #[ink(message)]
        pub fn validate_winner(
            &self,
            winner_total_score: u128,
            assignments: Vec<AssignmentInput>,
        ) -> bool {
            // ------------------------------
            // 1) Check for duplicate request_id
            // ------------------------------
            //
            // We use a simple O(n^2) check to avoid extra data structures.
            // This is acceptable as long as the number of assignments per slot
            // is not extremely large.
            let len = assignments.len();
            for i in 0..len {
                let j_start = i.checked_add(1).unwrap();
                for j in j_start..len {
                    if assignments[i].request_id == assignments[j].request_id {
                        // Same request appears more than once in the winning proposal.
                        return false;
                    }
                }
            }

            // ------------------------------
            // 2) Check that total score matches sum(pair_score)
            // ------------------------------
            let mut computed_total: u128 = 0;
            for a in assignments.iter() {
                // Use saturating_add for safety (avoid panics on overflow).
                computed_total = computed_total.saturating_add(a.pair_score);
            }

            if computed_total != winner_total_score {
                return false;
            }

            // If we reach here, both checks passed.
            true
        }
    }

    // -------------------------------------------------------------------------
    // Original unit tests (from template) - still valid
    // They only test the flip/get logic and do not touch our new validation.
    // -------------------------------------------------------------------------
    #[cfg(test)]
    mod tests {
        /// Imports all the definitions from the outer scope so we can use them here.
        use super::*;

        /// We test if the default constructor does its job.
        #[ink::test]
        fn default_works() {
            let escrow = Escrow::default();
            assert_eq!(escrow.get(), false);
        }

        /// We test a simple use case of our contract.
        #[ink::test]
        fn it_works() {
            let mut escrow = Escrow::new(false);
            assert_eq!(escrow.get(), false);
            escrow.flip();
            assert_eq!(escrow.get(), true);
        }
    }

    // -------------------------------------------------------------------------
    // Original E2E tests (from template) - unchanged
    // -------------------------------------------------------------------------
    /// This is how you'd write end-to-end (E2E) or integration tests for ink! contracts.
    ///
    /// When running these you need to make sure that you:
    /// - Compile the tests with the `e2e-tests` feature flag enabled (`--features e2e-tests`)
    /// - Are running a Substrate node which contains `pallet-contracts` in the background
    #[cfg(all(test, feature = "e2e-tests"))]
    mod e2e_tests {
        /// Imports all the definitions from the outer scope so we can use them here.
        use super::*;

        /// A helper function used for calling contract messages.
        use ink_e2e::ContractsBackend;

        /// The End-to-End test `Result` type.
        type E2EResult<T> = std::result::Result<T, Box<dyn std::error::Error>>;

        /// We test that we can upload and instantiate the contract using its default constructor.
        #[ink_e2e::test]
        async fn default_works(mut client: ink_e2e::Client<C, E>) -> E2EResult<()> {
            // Given
            let mut constructor = EscrowRef::default();

            // When
            let contract = client
                .instantiate("escrow", &ink_e2e::alice(), &mut constructor)
                .submit()
                .await
                .expect("instantiate failed");
            let call_builder = contract.call_builder::<Escrow>();

            // Then
            let get = call_builder.get();
            let get_result = client.call(&ink_e2e::alice(), &get).dry_run().await?;
            assert!(matches!(get_result.return_value(), false));

            Ok(())
        }

        /// We test that we can read and write a value from the on-chain contract.
        #[ink_e2e::test]
        async fn it_works(mut client: ink_e2e::Client<C, E>) -> E2EResult<()> {
            // Given
            let mut constructor = EscrowRef::new(false);
            let contract = client
                .instantiate("escrow", &ink_e2e::bob(), &mut constructor)
                .submit()
                .await
                .expect("instantiate failed");
            let mut call_builder = contract.call_builder::<Escrow>();

            let get = call_builder.get();
            let get_result = client.call(&ink_e2e::bob(), &get).dry_run().await?;
            assert!(matches!(get_result.return_value(), false));

            // When
            let flip = call_builder.flip();
            let _flip_result = client
                .call(&ink_e2e::bob(), &flip)
                .submit()
                .await
                .expect("flip failed");

            // Then
            let get = call_builder.get();
            let get_result = client.call(&ink_e2e::bob(), &get).dry_run().await?;
            assert!(matches!(get_result.return_value(), true));

            Ok(())
        }
    }
}
