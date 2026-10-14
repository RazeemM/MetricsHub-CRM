/** Human-readable labels for the enumerations stored by the API. */
export const ACCOUNT_TYPES: Record<string, string> = {
  prospect: 'Prospect',
  customer: 'Customer',
  platform_partner: 'Platform partner',
  reseller: 'Reseller',
  msp: 'MSP',
  system_integrator: 'System integrator',
  other: 'Other',
}
export const CONTACT_ROLES: Record<string, string> = {
  customer_contact: 'Customer contact',
  platform_account_manager: 'Platform account manager',
  partner_contact: 'Partner contact',
  technical: 'Technical',
  economic_buyer: 'Economic buyer',
  champion: 'Champion',
  other: 'Other',
}
export const LIFECYCLES: Record<string, string> = {
  lead: 'Lead',
  qualified: 'Qualified',
  customer: 'Customer',
  disqualified: 'Disqualified',
}
export const LEAD_SOURCES: Record<string, string> = {
  platform_referral: 'Platform referral',
  website_contact: 'Website contact form',
  quote_request: 'Quote request',
  download: 'Download',
  trial: 'Trial',
  partner_signup: 'Partner sign-up',
  direct: 'Direct',
  event: 'Event',
  marketplace: 'Marketplace',
  import: 'Import',
  other: 'Other',
}
export const ROUTES: Record<string, string> = {
  direct: 'Direct',
  bmc_marketzone: 'BMC MarketZone',
  marketplace: 'Marketplace',
  reseller: 'Reseller',
}
export const DEAL_TYPES: Record<string, string> = { new: 'New', expansion: 'Expansion', renewal: 'Renewal' }
export const UNITS: Record<string, string> = {
  host: 'Host',
  resource_unit: 'Resource unit (RU)',
  physical_system: 'Physical system',
  front_end_ports_5: '5 front-end ports',
  service_day: 'Service day',
  license: 'License',
  other: 'Other',
}
export const CHANNELS: Record<string, string> = {
  direct: 'Direct',
  bmc: 'BMC',
  marketplace: 'Marketplace',
  reseller: 'Reseller',
}

export const toOptions = (m: Record<string, string>) => Object.entries(m).map(([value, label]) => ({ value, label }))

export function money(value: string | number | null | undefined, currency = 'USD') {
  const n = Number(value ?? 0)
  try {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency, maximumFractionDigits: 0 }).format(n)
  } catch {
    return `${currency} ${n.toFixed(0)}`
  }
}

export function money2(value: string | number | null | undefined, currency = 'USD') {
  const n = Number(value ?? 0)
  try {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(n)
  } catch {
    return `${currency} ${n.toFixed(2)}`
  }
}

export function fmtDate(d: string | null | undefined) {
  if (!d) return '—'
  const date = new Date(d.length === 10 ? `${d}T00:00:00` : d)
  return date.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
}

export const LIFECYCLE_COLORS: Record<string, string> = {
  lead: 'blue',
  qualified: 'violet',
  customer: 'green',
  disqualified: 'gray',
}
export const ACCOUNT_TYPE_COLORS: Record<string, string> = {
  prospect: 'blue',
  customer: 'green',
  platform_partner: 'orange',
  reseller: 'grape',
  msp: 'cyan',
  system_integrator: 'teal',
  other: 'gray',
}
