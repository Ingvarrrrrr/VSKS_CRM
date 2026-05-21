from app.models.organization import Organization
from app.models.user import User
from app.models.contractor import Contractor
from app.models.contract import Contract
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.purchase_file import PurchaseFile
from app.models.payment import Payment
from app.models.feo_category import FeoCategory
from app.models.subsidy import Subsidy
from app.models.product import Product
from app.models.platform_publication import PlatformPublication
from app.models.subsidy_approver import SubsidyApprover
from app.models.responsible_person import ResponsiblePerson
from app.models.commercial_request import CommercialRequest, CommercialRequestRecipient
from app.models.supplier import Supplier, SupplierProduct
from app.models.system_incident import SystemIncident
from app.models.purchase_event import PurchaseMember, PurchaseEvent
from app.models.user_hierarchy import UserHierarchy
from app.models.user_org_access import UserOrgAccess
from app.models.subsidy_contractor_override import SubsidyContractorOverride
from app.models.event import Event
from app.models.purchase_approval import PurchaseApproval
from app.models.approval_signature_key import ApprovalSignatureKey
from app.models.task import Task
from app.models.task_comment import TaskComment
from app.models.department import Department, DepartmentMember, TaskEditDelegate
from app.models.org_section_config import OrgSectionConfig
from app.models.delivery_address import DeliveryAddress
from app.models.feo_planned_item import FeoPlannedItem
from app.models.system_setting import SystemSetting
from app.models.manager_organization import ManagerOrganization
from app.models.user_organization import UserOrganization
from app.models.task_change import TaskChange, TaskFieldSeen
from app.models.budget_history import BudgetHistory
from app.models.chat_room import ChatRoom, ChatParticipant  # noqa: F401
from app.models.chat_message import ChatMessage, MessageRead  # noqa: F401
from app.models.wish import Wish  # noqa: F401
from app.models.wish_item import WishItem  # noqa: F401
from app.models.push_subscription import PushSubscription  # noqa: F401
from app.models.permission import PermissionTab, PermissionAction, RolePermission, UserOrgPermissionOverride  # noqa: F401
from app.models.purchase_receipt import PurchaseReceipt  # noqa: F401
from app.models.user_address import UserAddress  # noqa: F401
from app.models.report_config import ReportConfig  # noqa: F401
from app.models.contract_item import ContractItem  # noqa: F401 — Phase 27.1: register ContractItem in Base.metadata
from app.models.plan_graph_version import PlanGraphVersion  # noqa: F401 — Phase 12-03: plan-graph versioning
# Phase 29: Vehicle Fleet models
from app.models.vehicle import Vehicle  # noqa: F401
from app.models.vehicle_attachment import VehicleAttachment  # noqa: F401
from app.models.vehicle_repair import VehicleRepair  # noqa: F401
from app.models.repair_attachment import RepairAttachment  # noqa: F401
from app.models.vehicle_field_history import VehicleFieldHistory  # noqa: F401
from app.models.vehicle_odometer import VehicleOdometer  # noqa: F401
from app.models.fuel_log import FuelLog  # noqa: F401
from app.models.external_driver import ExternalDriver  # noqa: F401
from app.models.trip import Trip  # noqa: F401
from app.models.vehicle_transfer_history import VehicleTransferHistory  # noqa: F401 — Phase 29.3
from app.models.vehicle_fine import VehicleFine  # noqa: F401 — Phase 29.3 fines
from app.models.fleet_document import FleetDocument  # noqa: F401 — Phase 30 vehicle documents
from app.models.waybill_children import RouteStop, OdometerReading, FuelRefill  # noqa: F401 — Phase 30
