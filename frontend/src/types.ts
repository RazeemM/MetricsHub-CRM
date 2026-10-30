export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}
export interface Ref {
  id: number
  name: string
}
export interface UserRef {
  id: number
  full_name: string
}
export interface User {
  id: number
  email: string
  full_name: string
  role: 'admin' | 'sales' | 'readonly'
  brand_id: number | null
  is_active: boolean
}
export interface Brand {
  id: number
  code: string
  name: string
  quote_prefix: string
  default_currency: string
}
export interface Account {
  id: number
  name: string
  account_type: string
  domain: string | null
  website: string | null
  industry: string | null
  country: string | null
  region: string | null
  city: string | null
  address: string | null
  phone: string | null
  vat_number: string | null
  parent_id: number | null
  owner_id: number | null
  owner: UserRef | null
  notes: string | null
  contact_count: number
  open_opportunity_count: number
  created_at: string
}
export interface Contact {
  id: number
  first_name: string | null
  last_name: string | null
  full_name: string
  email: string | null
  previous_emails?: string[]
  phone: string | null
  mobile: string | null
  job_title: string | null
  account_id: number | null
  account: Ref | null
  role: string
  lifecycle: string
  source: string | null
  brand_id: number | null
  owner_id: number | null
  owner: UserRef | null
  country: string | null
  linkedin: string | null
  consent_marketing: boolean
  unsubscribed: boolean
  notes: string | null
  created_at: string
}
export interface Price {
  price_book_id: number
  price_book: string
  currency: string
  unit_price: string
}
export interface Product {
  id: number
  brand_id: number
  sku: string
  name: string
  description: string | null
  unit: string
  billing_type: 'recurring' | 'one_time'
  active: boolean
  prices: Price[]
}
export interface PriceBook {
  id: number
  name: string
  brand_id: number | null
  currency: string
  channel: string
  is_default: boolean
  active: boolean
  entries: { product_id: number; unit_price: string }[]
}
export interface Stage {
  id: number
  name: string
  position: number
  probability: number
  kind: 'open' | 'won' | 'lost'
}
export interface Pipeline {
  id: number
  name: string
  kind: string
  stages: Stage[]
}
export interface LineItem {
  id?: number
  product_id: number | null
  name: string
  description?: string | null
  unit?: string | null
  billing_type: 'recurring' | 'one_time'
  quantity: string | number
  unit_price: string | number
  discount_pct: string | number
  term_months: number | null
  fixed_total?: string | number | null
  line_total?: string
}
export interface Opportunity {
  id: number
  title: string
  account_id: number
  account: Ref
  brand_id: number
  brand: Ref
  owner_id: number | null
  owner: UserRef | null
  pipeline_id: number
  stage_id: number
  stage: Stage
  deal_type: string
  lead_source: string | null
  referring_platform_id: number | null
  referring_platform: Ref | null
  partner_contact_id: number | null
  partner_contact: Contact | null
  primary_contact_id: number | null
  primary_contact: Contact | null
  route_to_market: string
  reseller_id: number | null
  reseller: Ref | null
  price_book_id: number | null
  currency: string
  expected_close_date: string | null
  contract_start: string | null
  contract_end: string | null
  term_months: number
  probability: number | null
  effective_probability: number
  amount_tcv: string
  amount_arr: string
  weighted_amount: string
  lost_reason: string | null
  description: string | null
  next_step: string | null
  closed_at: string | null
  line_items: LineItem[]
  created_at: string
  updated_at: string
}
export interface Activity {
  id: number
  type: 'note' | 'task' | 'call' | 'meeting' | 'email'
  subject: string
  body: string | null
  due_at: string | null
  completed_at: string | null
  owner: UserRef | null
  account_id: number | null
  contact_id: number | null
  opportunity_id: number | null
  created_at: string
}
