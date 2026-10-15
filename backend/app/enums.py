"""Enumerations stored as plain strings (easy to extend without DB enum migrations)."""
from enum import StrEnum


class UserRole(StrEnum):
    admin = "admin"
    sales = "sales"
    readonly = "readonly"


class AccountType(StrEnum):
    prospect = "prospect"
    customer = "customer"
    platform_partner = "platform_partner"  # BMC, Datadog, Splunk, Grafana...
    reseller = "reseller"
    msp = "msp"
    system_integrator = "system_integrator"
    other = "other"


class ContactRole(StrEnum):
    customer_contact = "customer_contact"
    platform_account_manager = "platform_account_manager"
    partner_contact = "partner_contact"
    technical = "technical"
    economic_buyer = "economic_buyer"
    champion = "champion"
    other = "other"


class Lifecycle(StrEnum):
    lead = "lead"
    qualified = "qualified"
    customer = "customer"
    disqualified = "disqualified"


class LeadSource(StrEnum):
    platform_referral = "platform_referral"
    website_contact = "website_contact"
    quote_request = "quote_request"
    download = "download"
    trial = "trial"
    partner_signup = "partner_signup"
    newsletter = "newsletter"
    direct = "direct"
    event = "event"
    marketplace = "marketplace"
    import_ = "import"
    other = "other"


class ProductUnit(StrEnum):
    host = "host"
    resource_unit = "resource_unit"
    physical_system = "physical_system"
    front_end_ports_5 = "front_end_ports_5"
    service_day = "service_day"
    license = "license"
    other = "other"


class BillingType(StrEnum):
    recurring = "recurring"  # unit price is per month
    one_time = "one_time"


class Channel(StrEnum):
    direct = "direct"
    bmc = "bmc"
    marketplace = "marketplace"
    reseller = "reseller"


class PipelineKind(StrEnum):
    new_business = "new_business"
    renewal = "renewal"


class StageKind(StrEnum):
    open = "open"
    won = "won"
    lost = "lost"


class DealType(StrEnum):
    new = "new"
    expansion = "expansion"
    renewal = "renewal"


class RouteToMarket(StrEnum):
    direct = "direct"
    bmc_marketzone = "bmc_marketzone"
    marketplace = "marketplace"
    reseller = "reseller"


class ActivityType(StrEnum):
    note = "note"
    task = "task"
    call = "call"
    meeting = "meeting"
    email = "email"
