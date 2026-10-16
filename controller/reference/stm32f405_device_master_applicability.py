"""TC-03B45 STM32F405/F407 non-CPU bus-master applicability gate.

Portable/offline reference only.

DS8626 Rev 12 (March 2026) states that Ethernet and the camera interface are
available only on STM32F407xx devices. Its Ethernet section explicitly says the
Ethernet MAC with dedicated DMA is available only on STM32F407xx. The same
datasheet states that STM32F405xx and STM32F407xx both embed USB OTG HS with an
internal USB DMA.

TC-03B43 intentionally used the superset bus-matrix master inventory from the
shared family reference manual:
- DMA1 memory;
- DMA2 memory;
- DMA2 peripheral;
- Ethernet DMA;
- USB OTG HS DMA.

For a verified STM32F405xx target, requiring an Ethernet-DMA runtime receipt is
over-conservative because that peripheral is architecturally absent. This gate
separates device-family applicability from runtime quiescence evidence.

The target family itself still needs provenance. A user statement or scenario
is useful for research planning but is not promoted into team acceptance. A
team-verified STM32F405xx identity may produce an explicit compatibility receipt
for B43 marking the architecturally absent Ethernet master as unable to access
memory.

This module does not:
- verify the physical MCU marking or schematic;
- infer the exact STM32F405 package/order code;
- disable Ethernet/USB/DMA;
- change the hard-coded B43 master list;
- authorize firmware, CAN, torque, shutdown, or vehicle changes.
"""

from __future__ import annotations
from dataclasses import asdict, dataclass
import json

SOURCE_KINDS={"scenario","user_statement","team_verified"}
SUPPORTED_FAMILIES={"STM32F405xx","STM32F407xx"}
B43_MASTERS=(
    "dma1_memory",
    "dma2_memory",
    "dma2_peripheral",
    "ethernet_dma",
    "usb_otg_hs_dma",
)
DEVICE_PRESENT={
    "STM32F405xx": frozenset({
        "dma1_memory","dma2_memory","dma2_peripheral","usb_otg_hs_dma"
    }),
    "STM32F407xx": frozenset(B43_MASTERS),
}
ARCHITECTURE_SOURCE="DS8626 Rev 12 (March 2026)"

class DeviceApplicabilityError(ValueError):
    pass

def _source(v:object)->str:
    if v not in SOURCE_KINDS:
        raise DeviceApplicabilityError(
            "source_kind must be scenario, user_statement, or team_verified"
        )
    return str(v)

@dataclass(frozen=True)
class DeviceIdentityEvidence:
    family:str
    source_kind:str
    board_revision:str|None=None
    receipt_ref:str|None=None
    def checked(self)->"DeviceIdentityEvidence":
        if self.family not in SUPPORTED_FAMILIES:
            raise DeviceApplicabilityError(
                "family must be STM32F405xx or STM32F407xx"
            )
        if self.board_revision is not None and (
            not isinstance(self.board_revision,str) or not self.board_revision.strip()
        ):
            raise DeviceApplicabilityError("board_revision must be non-empty or None")
        if self.receipt_ref is not None and (
            not isinstance(self.receipt_ref,str) or not self.receipt_ref.strip()
        ):
            raise DeviceApplicabilityError("receipt_ref must be non-empty or None")
        return DeviceIdentityEvidence(
            family=self.family,
            source_kind=_source(self.source_kind),
            board_revision=self.board_revision.strip() if self.board_revision else None,
            receipt_ref=self.receipt_ref.strip() if self.receipt_ref else None,
        )

@dataclass(frozen=True)
class MasterApplicability:
    master:str
    present_on_family:bool
    status:str
    architecture_source:str=ARCHITECTURE_SOURCE

@dataclass(frozen=True)
class DeviceMasterAssessment:
    schema:str
    family:str
    device_source_kind:str
    applicable_masters:tuple[str,...]
    architecturally_absent_masters:tuple[str,...]
    master_assessments:tuple[MasterApplicability,...]
    exact_family_team_verified:bool
    ready_to_prune_b43_inventory:bool
    architecture_source:str
    blockers:tuple[str,...]
    physical_board_identity_proven:bool=False
    runtime_quiescence_proven:bool=False
    actual_contention_observed:bool=False
    peripheral_change_selected:bool=False
    firmware_change_authorized:bool=False
    vehicle_acceptance_proven:bool=False
    action_authority:bool=False
    def to_json(self)->str:
        return json.dumps(asdict(self),sort_keys=True,separators=(",",":"),allow_nan=False)

def assess_device_master_applicability(
    evidence:DeviceIdentityEvidence,
)->DeviceMasterAssessment:
    e=evidence.checked()
    present=DEVICE_PRESENT[e.family]
    applicable=tuple(m for m in B43_MASTERS if m in present)
    absent=tuple(m for m in B43_MASTERS if m not in present)
    exact=e.source_kind=="team_verified"
    blockers=[]
    if not exact:
        blockers.append("device_family_not_team_verified")
    masters=tuple(
        MasterApplicability(
            master=m,
            present_on_family=(m in present),
            status="present_runtime_evidence_required" if m in present
                   else "architecturally_absent_for_family",
        ) for m in B43_MASTERS
    )
    return DeviceMasterAssessment(
        schema="enme408-tc03b45-device-master-applicability/v1",
        family=e.family,
        device_source_kind=e.source_kind,
        applicable_masters=applicable,
        architecturally_absent_masters=absent,
        master_assessments=masters,
        exact_family_team_verified=exact,
        ready_to_prune_b43_inventory=exact,
        architecture_source=ARCHITECTURE_SOURCE,
        blockers=tuple(blockers),
        physical_board_identity_proven=exact,
    )

def make_b43_absence_receipts(evidence:DeviceIdentityEvidence):
    """Return standalone compatibility receipts for B43-style consumers.

    No B43 module import is required. Architecturally absent masters are
    represented as unable to access memory only when the device identity is
    team-verified. A consumer may translate these dictionaries into its own
    observation type while retaining `reason=architecturally_absent`.
    """
    result=assess_device_master_applicability(evidence)
    if not result.ready_to_prune_b43_inventory:
        raise DeviceApplicabilityError(
            "team-verified device family required for B43 absence receipts"
        )
    return tuple(
        {
            "master":m,
            "quiescent_for_exception_window":True,
            "possible_access_windows":(),
            "all_possible_memory_accesses_covered":True,
            "source_kind":"team_verified",
            "reason":"architecturally_absent",
        }
        for m in result.architecturally_absent_masters
    )

def frozen_f405_ethernet_counterexample()->dict[str,object]:
    """The shared-family B43 inventory contains a master absent on F405xx."""
    r=assess_device_master_applicability(
        DeviceIdentityEvidence("STM32F405xx","user_statement")
    )
    return {
        "schema":"enme408-tc03b45-f405-ethernet-counterexample/v1",
        "device_identity_source":"user_statement",
        "family":r.family,
        "b43_superset_contains_ethernet":("ethernet_dma" in B43_MASTERS),
        "ethernet_present_on_f405":("ethernet_dma" in r.applicable_masters),
        "usb_otg_hs_dma_present_on_f405":(
            "usb_otg_hs_dma" in r.applicable_masters
        ),
        "ready_to_prune_team_inventory":r.ready_to_prune_b43_inventory,
        "lesson":"family_applicability_precedes_runtime_master_inventory",
        "action_authority":False,
    }
