import { Button, Card, Grid, Group, NumberInput, SegmentedControl, Select, SimpleGrid, Stack, Text, Textarea, TextInput, Title } from '@mantine/core'
import { DateInput } from '@mantine/dates'
import { notifications } from '@mantine/notifications'
import { useQuery } from '@tanstack/react-query'
import dayjs from 'dayjs'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { AccountPicker, ContactPicker, PageHeader, UserPicker } from '../components/common'
import { fromLineItem, LineItemsEditor, type DraftLine } from '../components/LineItemsEditor'
import { useApiMutation, useBrands, usePipelines, usePriceBooks, useProducts } from '../hooks'
import { DEAL_TYPES, LEAD_SOURCES, ROUTES, toOptions } from '../labels'
import type { Account, Contact, Opportunity } from '../types'

interface Form {
  title: string
  account_id: number | null
  brand_id: number | null
  owner_id: number | null
  stage_id: number | null
  deal_type: string
  lead_source: string | null
  referring_platform_id: number | null
  partner_contact_id: number | null
  primary_contact_id: number | null
  route_to_market: string
  reseller_id: number | null
  price_book_id: number | null
  expected_close_date: string | null
  contract_start: string | null
  term_months: number
  probability: number | null
  next_step: string
  description: string
}

const toDate = (s: string | null) => (s ? dayjs(s).toDate() : null)
const fromDate = (d: unknown) => (d ? dayjs(d as Date).format('YYYY-MM-DD') : null)

export default function OpportunityEdit() {
  const params = useParams()
  const id = params.id ? Number(params.id) : null
  const [search] = useSearchParams()
  const nav = useNavigate()
  const { user } = useAuth()
  const { data: brands } = useBrands()
  const { data: pipelines } = usePipelines()
  const { data: books } = usePriceBooks()
  const { data: existing } = useQuery({ queryKey: ['opportunity', id], queryFn: () => api<Opportunity>(`/opportunities/${id}`), enabled: !!id })
  const presetAccount = Number(search.get('account_id')) || null
  const { data: presetAcc } = useQuery({
    queryKey: ['account', presetAccount],
    queryFn: () => api<Account>(`/accounts/${presetAccount}`),
    enabled: !!presetAccount && !id,
  })
  const presetContact = Number(search.get('primary_contact_id')) || null
  const { data: presetCt } = useQuery({
    queryKey: ['contact', presetContact],
    queryFn: () => api<Contact>(`/contacts/${presetContact}`),
    enabled: !!presetContact && !id,
  })

  const [f, setF] = useState<Form | null>(null)
  const [lines, setLines] = useState<DraftLine[]>([])
  const set = <K extends keyof Form>(k: K) => (v: Form[K]) => setF((s) => (s ? { ...s, [k]: v } : s))

  useEffect(() => {
    if (f) return
    if (id && existing) {
      setF({
        title: existing.title,
        account_id: existing.account_id,
        brand_id: existing.brand_id,
        owner_id: existing.owner_id,
        stage_id: existing.stage_id,
        deal_type: existing.deal_type,
        lead_source: existing.lead_source,
        referring_platform_id: existing.referring_platform_id,
        partner_contact_id: existing.partner_contact_id,
        primary_contact_id: existing.primary_contact_id,
        route_to_market: existing.route_to_market,
        reseller_id: existing.reseller_id,
        price_book_id: existing.price_book_id,
        expected_close_date: existing.expected_close_date,
        contract_start: existing.contract_start,
        term_months: existing.term_months,
        probability: existing.probability,
        next_step: existing.next_step ?? '',
        description: existing.description ?? '',
      })
      setLines(existing.line_items.map(fromLineItem))
    } else if (!id && brands) {
      const brand = brands.find((b) => b.id === user?.brand_id) ?? brands[0]
      setF({
        title: '',
        account_id: presetAccount,
        brand_id: brand?.id ?? null,
        owner_id: user?.id ?? null,
        stage_id: null,
        deal_type: 'new',
        lead_source: null,
        referring_platform_id: null,
        partner_contact_id: null,
        primary_contact_id: presetContact,
        route_to_market: 'direct',
        reseller_id: null,
        price_book_id: null,
        expected_close_date: dayjs().add(90, 'day').format('YYYY-MM-DD'),
        contract_start: null,
        term_months: 12,
        probability: null,
        next_step: '',
        description: '',
      })
    }
  }, [id, existing, brands, user, f, presetAccount, presetContact])

  const brandBooks = useMemo(() => (books ?? []).filter((b) => b.active && (!f?.brand_id || b.brand_id === f.brand_id)), [books, f?.brand_id])
  // pick the brand's default price book when brand changes
  useEffect(() => {
    if (!f || !books) return
    if (f.price_book_id && brandBooks.some((b) => b.id === f.price_book_id)) return
    const def = brandBooks.find((b) => b.is_default) ?? brandBooks[0]
    if (def && def.id !== f.price_book_id) setF((s) => (s ? { ...s, price_book_id: def.id } : s))
  }, [brandBooks, books, f])

  const priceBook = books?.find((b) => b.id === f?.price_book_id)
  const { data: products } = useProducts(f?.brand_id)
  const currency = priceBook?.currency ?? existing?.currency ?? 'USD'
  const pipelineKind = f?.deal_type === 'renewal' ? 'renewal' : 'new_business'
  const pipeline = existing && f?.stage_id ? pipelines?.find((p) => p.stages.some((s) => s.id === f.stage_id)) : pipelines?.find((p) => p.kind === pipelineKind)
  const allStages = (pipelines ?? []).flatMap((p) => p.stages.map((s) => ({ ...s, pipeline: p.name })))

  const save = useApiMutation(
    (body: unknown) => (id ? api<Opportunity>(`/opportunities/${id}`, { method: 'PATCH', body }) : api<Opportunity>('/opportunities', { method: 'POST', body })),
    {
      invalidate: [['opportunities'], ['opportunity'], ['board'], ['dashboard'], ['accounts'], ['account']],
      success: id ? 'Opportunity saved' : 'Opportunity created',
      onSuccess: (o) => nav(`/opportunities/${o.id}`),
    },
  )

  if (!f)
    return (
      <Text c="dimmed" p="md">
        Loading…
      </Text>
    )

  const contractEnd = f.contract_start ? dayjs(f.contract_start).add(f.term_months, 'month').subtract(1, 'day').format('DD MMM YYYY') : null

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!f.account_id || !f.brand_id) {
      notifications.show({ color: 'red', message: 'Account and brand are required' })
      return
    }
    const bad = lines.find((l) => !l.product_id && !l.name.trim())
    if (bad) {
      notifications.show({ color: 'red', message: 'Give every custom line a name' })
      return
    }
    save.mutate({
      ...f,
      stage_id: f.stage_id ?? undefined,
      next_step: f.next_step || null,
      description: f.description || null,
      line_items: lines.map((l) => ({
        product_id: l.product_id,
        name: l.product_id ? undefined : l.name,
        description: l.description || null,
        unit: l.product_id || l.unit !== 'deal_total' ? undefined : l.unit,
        quantity: l.quantity,
        unit_price: l.unit_price,
        discount_pct: l.discount_pct,
        term_months: l.billing_type === 'recurring' ? l.term_months : null,
        billing_type: l.billing_type,
      })),
    })
  }

  return (
    <form onSubmit={submit}>
      <PageHeader
        title={id ? 'Edit opportunity' : 'New opportunity'}
        actions={
          <>
            <Button variant="default" onClick={() => nav(-1)}>
              Cancel
            </Button>
            <Button type="submit" loading={save.isPending}>
              Save
            </Button>
          </>
        }
      />
      <Stack>
        <Card withBorder>
          <Grid>
            <Grid.Col span={{ base: 12, md: 8 }}>
              <TextInput label="Title" required placeholder="e.g. Acme Bank – MetricsHub Enterprise 500 hosts" value={f.title} onChange={(e) => set('title')(e.target.value)} />
            </Grid.Col>
            <Grid.Col span={{ base: 12, md: 4 }}>
              <Stack gap={4}>
                <Text size="sm" fw={500}>
                  Brand
                </Text>
                <SegmentedControl
                  fullWidth
                  data={(brands ?? []).map((b) => ({ value: String(b.id), label: b.name }))}
                  value={String(f.brand_id ?? '')}
                  onChange={(v) => setF({ ...f, brand_id: Number(v), price_book_id: null })}
                />
              </Stack>
            </Grid.Col>
          </Grid>
          <SimpleGrid cols={{ base: 1, sm: 2, md: 4 }} mt="sm">
            <AccountPicker label="Account" required allowCreate value={f.account_id} initialLabel={existing?.account.name ?? presetAcc?.name} onChange={set('account_id')} />
            <ContactPicker
              label="Primary contact"
              allowCreate
              value={f.primary_contact_id}
              accountId={f.account_id}
              initialLabel={existing?.primary_contact?.full_name ?? presetCt?.full_name}
              onChange={set('primary_contact_id')}
            />
            <UserPicker label="Opportunity owner" value={f.owner_id} onChange={set('owner_id')} />
            <Select label="Deal type" data={toOptions(DEAL_TYPES)} value={f.deal_type} onChange={(v) => set('deal_type')(v ?? 'new')} allowDeselect={false} disabled={!!id} />
            <Select
              label="Stage"
              data={
                id
                  ? (pipelines ?? []).map((p) => ({ group: p.name, items: p.stages.map((s) => ({ value: String(s.id), label: `${s.name} (${s.probability}%)` })) }))
                  : (pipeline?.stages ?? []).map((s) => ({ value: String(s.id), label: `${s.name} (${s.probability}%)` }))
              }
              placeholder={pipeline?.stages[0]?.name}
              value={f.stage_id ? String(f.stage_id) : null}
              onChange={(v) => set('stage_id')(v ? Number(v) : null)}
            />
            <NumberInput
              label="Probability override %"
              placeholder={String(allStages.find((s) => s.id === f.stage_id)?.probability ?? pipeline?.stages[0]?.probability ?? '')}
              min={0}
              max={100}
              value={f.probability ?? ''}
              onChange={(v) => set('probability')(v === '' ? null : Number(v))}
            />
            <DateInput label="Expected close" value={toDate(f.expected_close_date)} onChange={(d) => set('expected_close_date')(fromDate(d))} clearable valueFormat="DD MMM YYYY" />
            <TextInput label="Next step" value={f.next_step} onChange={(e) => set('next_step')(e.target.value)} />
          </SimpleGrid>
        </Card>

        <Card withBorder>
          <Title order={5} mb="sm">
            Source &amp; channel
          </Title>
          <SimpleGrid cols={{ base: 1, sm: 2, md: 4 }}>
            <Select label="Lead source" data={toOptions(LEAD_SOURCES)} value={f.lead_source} onChange={set('lead_source')} clearable />
            <AccountPicker
              label="Referring platform"
              types={['platform_partner']}
              allowCreate
              value={f.referring_platform_id}
              initialLabel={existing?.referring_platform?.name}
              onChange={(v) => setF({ ...f, referring_platform_id: v, partner_contact_id: v ? f.partner_contact_id : null })}
              placeholder="BMC, Datadog, Splunk…"
            />
            <ContactPicker
              label="Platform account manager"
              accountId={f.referring_platform_id}
              roles={['platform_account_manager', 'partner_contact']}
              allowCreate
              value={f.partner_contact_id}
              initialLabel={existing?.partner_contact?.full_name}
              onChange={set('partner_contact_id')}
              disabled={!f.referring_platform_id}
            />
            <Select label="Route to market" data={toOptions(ROUTES)} value={f.route_to_market} onChange={(v) => set('route_to_market')(v ?? 'direct')} allowDeselect={false} />
            {f.route_to_market === 'reseller' && (
              <AccountPicker label="Reseller" types={['reseller', 'msp', 'system_integrator']} allowCreate value={f.reseller_id} initialLabel={existing?.reseller?.name} onChange={set('reseller_id')} />
            )}
          </SimpleGrid>
        </Card>

        <Card withBorder>
          <Group justify="space-between" mb="sm">
            <Title order={5}>Products &amp; pricing</Title>
          </Group>
          <SimpleGrid cols={{ base: 1, sm: 2, md: 4 }} mb="sm">
            <Select
              label="Price book"
              data={brandBooks.map((b) => ({ value: String(b.id), label: `${b.name} (${b.currency})` }))}
              value={f.price_book_id ? String(f.price_book_id) : null}
              onChange={(v) => set('price_book_id')(v ? Number(v) : null)}
              description="Sets currency and default unit prices"
            />
            <DateInput label="Contract start" value={toDate(f.contract_start)} onChange={(d) => set('contract_start')(fromDate(d))} clearable valueFormat="DD MMM YYYY" />
            <NumberInput label="Contract period (months)" min={1} max={120} value={f.term_months} onChange={(v) => set('term_months')(Number(v) || 12)} />
            <TextInput label="Contract end" value={contractEnd ?? ''} readOnly placeholder="Set a start date" />
          </SimpleGrid>
          <LineItemsEditor lines={lines} onChange={setLines} products={products ?? []} priceBook={priceBook} term={f.term_months} currency={currency} brandId={f.brand_id} />
        </Card>

        <Card withBorder>
          <Textarea label="Description" autosize minRows={3} value={f.description} onChange={(e) => set('description')(e.target.value)} />
        </Card>
      </Stack>
    </form>
  )
}
