#ifndef ENME408_TORQUE_CONTRACT_H
#define ENME408_TORQUE_CONTRACT_H

/* Portable host prototype. No firmware, transport, physical wheel mapping,
 * scheduling, motor enable, or independent shutdown authority is defined. */
#include <stddef.h>
#include <stdint.h>

#if defined(_WIN32)
#define TC_API __declspec(dllexport)
#else
#define TC_API
#endif

#define TC_ABI_VERSION 1u
#define TC_NUMERIC_CONTRACT_VERSION 2u
#define TC_WHEELS 4u
#define TC_TEXT_CAPACITY 64u

enum tc_text_kind { TC_TEXT_NONE = 0, TC_TEXT_STRING = 1, TC_TEXT_INVALID = 2 };
enum tc_allocation_status { TC_ALLOCATION_INVALID = 0, TC_ALLOCATION_OK = 1,
    TC_ALLOCATION_SATURATED = 2, TC_ALLOCATION_FAULT = 3 };
enum tc_guard_status { TC_GUARD_INVALID = 0, TC_GUARD_OK = 1,
    TC_GUARD_LIMITED = 2, TC_GUARD_INHIBITED = 3 };
enum tc_fault_state { TC_STATE_INVALID = 0, TC_READY = 1, TC_LIMITED = 2,
    TC_INHIBITED = 3, TC_RECOVERY_PENDING = 4 };
enum tc_contract_code {
    TC_CONTRACT_OK = 0,
    TC_INVALID_CANDIDATE_TYPE = 1,
    TC_INVALID_CANDIDATE_STATUS = 2,
    TC_INVALID_CANDIDATE_OUTPUT = 3,
    TC_INVALID_CANDIDATE_DELIVERED = 4,
    TC_CANDIDATE_SUM_MISMATCH = 5,
    TC_INVALID_CANDIDATE_REQUESTED = 6,
    TC_INVALID_CANDIDATE_FAULT = 7,
    TC_CANDIDATE_STATUS_FAULT_MISMATCH = 8,
    TC_CANDIDATE_EXCEEDS_REQUEST = 9
};
enum tc_size_kind { TC_SIZE_SCALAR = 1, TC_SIZE_TEXT = 2, TC_SIZE_ALLOCATION = 3,
    TC_SIZE_GUARD = 4, TC_SIZE_SNAPSHOT = 5, TC_SIZE_POLICY = 6,
    TC_SIZE_CYCLE = 7, TC_SIZE_DECISION = 8 };

/* Numeric validity is an explicit decoder obligation: exactly 1 represents an
 * ordinary numeric scalar; every other tag represents a malformed source.
 * A decoder must NOT coerce booleans, strings or arbitrary objects to numbers. */
typedef struct { double value; uint8_t numeric; } tc_scalar;
/* String kind requires a terminating NUL within the fixed buffer. NONE ignores
 * its buffer. Text is a diagnostic identifier, never a CAN message or unit. */
typedef struct { uint8_t kind; char value[TC_TEXT_CAPACITY]; } tc_text;
typedef struct {
    uint8_t type_valid;
    uint8_t status;
    uint8_t wheel_vector_valid;
    tc_scalar wheels[TC_WHEELS];
    tc_scalar requested;
    tc_scalar delivered;
    tc_text fault;
} tc_allocation;
typedef struct {
    uint8_t status;
    uint8_t output_valid;
    tc_scalar output[TC_WHEELS];
    tc_text reason;
} tc_guard;
typedef struct {
    uint8_t state;
    uint32_t recovery_streak;
    uint32_t generation;
} tc_snapshot;
typedef struct { uint32_t valid_samples_to_recover; } tc_policy;
typedef struct {
    tc_allocation allocation;
    tc_guard guard;
    tc_text clock_fault;
    uint8_t restart_requested;
} tc_cycle;
typedef struct {
    tc_snapshot next;
    uint8_t command_allowed;
    double command[TC_WHEELS];
    char reason[TC_TEXT_CAPACITY];
    uint32_t contract_code;
} tc_decision;

/* Valid pointers must refer to correctly aligned, complete objects. Input and
 * output storage must not overlap. These are host ABI structures, NOT a packed
 * wire format. No allocation is performed. */
TC_API uint32_t tc_abi_version(void);
TC_API uint32_t tc_numeric_contract_version(void);
TC_API size_t tc_abi_sizeof(uint32_t kind);
TC_API void tc_init_snapshot(tc_snapshot *snapshot);
TC_API uint32_t tc_validate_allocation(const tc_allocation *candidate);
TC_API const char *tc_contract_reason(uint32_t code);
/* Final gate consumes an already computed guard result; it does NOT implement
 * the allocator, pedal logic, slew limiter, clock normalization or persistence.
 * They remain external, independently tested owners. Invalid inputs inhibit.
 * Return 0 for a decision, 1 if a required pointer was NULL. A non-NULL output
 * is initialized to an inhibited, exactly-zero vector before any validation. */
TC_API uint32_t tc_decide(const tc_snapshot *previous, const tc_cycle *cycle,
                          const tc_policy *policy, tc_decision *output);

#endif
