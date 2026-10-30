import { ActionIcon, Badge, Button, Group, Modal, NumberInput, Paper, ScrollArea, Select, SimpleGrid, Stack, Table, Text, TextInput } from '@mantine/core'
import { IconPlus, IconStack2, IconTrash } from '@tabler/icons-react'
import { useState } from 'react'
import { api } from '../api'
import { useAuth } from '../auth'
import { useApiMutation } from '../hooks'
import { money, money2, toOptions, UNITS } from '../labels'
import type { LineItem, PriceBook, Product } from '../types'

export interface DraftLine {
  key: string
  product_id: number | null
  name: string
  description?: string | null
  billing_type: 'recurring' | 'one_time'
  unit: string | null
  quantity: number
  unit_price: number
  discount_pct: number
  term_months: number | null
  /** The line's agreed value (an imported quote's total charge): the price and discount are kept for reference. */
  fixed_total?: number | null
}

/** A line holding the total value of several products, with no per-product breakdown. */
export const DEAL_TOTAL = 'deal_total'
export const isDealTotal = (l: DraftLine) => !l.product_id && l.unit === DEAL_TOTAL
const MULTIPLE = '__multiple'
const NEW_PRODUCT = '__new_product'

/** Mirrors backend pricing.py so the user sees totals as they type. */
export function lineTotal(l: DraftLine, defaultTerm: number) {
  if (l.fixed_total != null) return l.fixed_total
  const base = l.quantity * l.unit_price * (1 - (l.discount_pct || 0) / 100)
  const total = l.billing_type === 'recurring' && !isDealTotal(l) ? base * (l.term_months || defaultTerm) : base
  return Math.round(total * 100) / 100
}

export function totals(lines: DraftLine[], term: number) {
  let tcv = 0
  let arr = 0
  let oneTime = 0
  for (const l of lines) {
    const t = lineTotal(l, term)
    tcv += t
    if (l.billing_type === 'recurring') arr += (t / (l.term_months || term)) * 12
    else oneTime += t
  }
  return { tcv, arr, oneTime }
}

export const fromLineItem = (li: LineItem): DraftLine => ({
  key: `li-${li.id ?? Math.random()}`,
  product_id: li.product_id,
  name: li.name,
  description: li.description,
  billing_type: li.billing_type,
  unit: li.unit ?? null,
  quantity: Number(li.quantity),
  unit_price: Number(li.unit_price),
  discount_pct: Number(li.discount_pct),
  term_months: li.term_months,
  fixed_total: li.fixed_total == null ? null : Number(li.fixed_total),
})

export function priceFor(product: Product, priceBook: PriceBook | undefined): number | null {
  const e = priceBook?.entries.find((x) => x.product_id === product.id)
  return e ? Number(e.unit_price) : null
}

export function LineItemsEditor({
  lines,
  onChange,
  products,
  priceBook,
  term,
  currency,
  readOnly,
  brandId,
}: {
  lines: DraftLine[]
  onChange: (l: DraftLine[]) => void
  products: Product[]
  priceBook?: PriceBook
  term: number
  currency: string
  readOnly?: boolean
  brandId?: number | null
}) {
  const { isAdmin } = useAuth()
  const [newProduct, setNewProduct] = useState<{ key: string; name: string } | null>(null)
  const update = (key: string, patch: Partial<DraftLine>) => onChange(lines.map((l) => (l.key === key ? { ...l, ...patch } : l)))
  // a new quantity, price, discount or term prices the line again instead of keeping its fixed total
  const reprice = (key: string, patch: Partial<DraftLine>) => update(key, { ...patch, fixed_total: null })
  const blank = (): DraftLine => ({ key: `n-${Date.now()}`, product_id: null, name: '', billing_type: 'recurring', unit: null, quantity: 1, unit_price: 0, discount_pct: 0, term_months: null })
  const multiple = { product_id: null, name: 'Multiple products', unit: DEAL_TOTAL, quantity: 1, discount_pct: 0 }
  const add = () => onChange([...lines, blank()])
  const addTotal = () => onChange([...lines, { ...blank(), ...multiple }])
  const pickProduct = (key: string, id: string | null, search: string) => {
    if (id === MULTIPLE) return update(key, multiple)
    if (id === NEW_PRODUCT) return setNewProduct({ key, name: search })
    const p = products.find((x) => String(x.id) === id)
    if (!p) return update(key, { product_id: null, unit: null })
    setProduct(key, p)
  }
  const setProduct = (key: string, p: Product) =>
    update(key, {
      product_id: p.id,
      name: p.name,
      billing_type: p.billing_type,
      unit: p.unit,
      unit_price: priceFor(p, priceBook) ?? 0,
    })
  const t = totals(lines, term)
  const productOptions = [
    { value: MULTIPLE, label: 'Multiple products · enter the total deal value' },
    ...products
      .filter((p) => p.active)
      .map((p) => {
        const price = priceFor(p, priceBook)
        return { value: String(p.id), label: `${p.name} (${p.sku})${price === null ? ' · no list price' : ''}` }
      }),
  ]

  return (
    <Stack gap="xs">
      <ScrollArea type="auto" offsetScrollbars>
        <Table verticalSpacing={6} miw={readOnly ? 560 : 900}>
          <Table.Thead>
            <Table.Tr>
              <Table.Th w={readOnly ? '40%' : '34%'}>Product</Table.Th>
              <Table.Th>Qty</Table.Th>
              <Table.Th>Unit price</Table.Th>
              <Table.Th>Discount %</Table.Th>
              <Table.Th>Term (mo.)</Table.Th>
              <Table.Th ta="right">Line total</Table.Th>
              <Table.Th />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {lines.map((l) => (
              <Table.Tr key={l.key}>
                <Table.Td>
                  <Stack gap={4}>
                    {readOnly ? (
                      <Text size="sm" fw={500}>
                        {l.name}
                      </Text>
                    ) : (
                      <ProductSelect
                        options={productOptions}
                        value={isDealTotal(l) ? MULTIPLE : l.product_id ? String(l.product_id) : null}
                        onPick={(v, search) => pickProduct(l.key, v, search)}
                        canCreate={isAdmin && !!brandId}
                      />
                    )}
                    {l.description && (
                      <Text size="xs" c="dimmed">
                        {l.description}
                      </Text>
                    )}
                    {!l.product_id && !readOnly && (
                      <TextInput placeholder={isDealTotal(l) ? 'Which products? e.g. Multiple products: Hardware, Storage' : 'Custom line name'} value={l.name} onChange={(e) => update(l.key, { name: e.target.value })} disabled={readOnly} />
                    )}
                    <Group gap={4}>
                      <Badge size="xs" variant="light" color={l.billing_type === 'recurring' ? 'violet' : 'orange'}>
                        {isDealTotal(l) ? (l.billing_type === 'recurring' ? 'total · licences / subscription' : 'total · one-time') : l.billing_type === 'recurring' ? 'per month' : 'one-time'}
                      </Badge>
                      {l.fixed_total != null && (
                        <Badge size="xs" variant="light" color="teal" title="The line is worth the total charge in the quote. Change its quantity, price, discount or term to price it again.">
                          quote total charge
                        </Badge>
                      )}
                      {l.unit && !isDealTotal(l) && (
                        <Badge size="xs" variant="outline" color="gray">
                          per {UNITS[l.unit] ?? l.unit}
                        </Badge>
                      )}
                      {!l.product_id && !readOnly && (
                        <Button
                          size="compact-xs"
                          variant="subtle"
                          onClick={() => update(l.key, { billing_type: l.billing_type === 'recurring' ? 'one_time' : 'recurring' })}
                        >
                          switch billing
                        </Button>
                      )}
                    </Group>
                  </Stack>
                </Table.Td>
                <Table.Td>
                  {isDealTotal(l) ? (
                    <Text size="sm" c="dimmed">
                      —
                    </Text>
                  ) : readOnly ? <Text size="sm">{l.quantity.toLocaleString('en-US')}</Text> : <NumberInput min={0} decimalScale={2} value={l.quantity} onChange={(v) => reprice(l.key, { quantity: Number(v) || 0 })} w={90} thousandSeparator />}
                </Table.Td>
                <Table.Td>
                  {readOnly ? <Text size="sm">{isDealTotal(l) ? 'Total' : money2(l.unit_price, currency)}</Text> : <NumberInput min={0} decimalScale={2} value={l.unit_price} onChange={(v) => reprice(l.key, { unit_price: Number(v) || 0 })} w={isDealTotal(l) ? 140 : 110} aria-label={isDealTotal(l) ? 'Total deal value' : 'Unit price'} prefix={currency === 'EUR' ? '€' : currency === 'USD' ? '$' : `${currency} `} thousandSeparator />}
                </Table.Td>
                <Table.Td>
                  {isDealTotal(l) ? (
                    <Text size="sm" c="dimmed">
                      —
                    </Text>
                  ) : readOnly ? <Text size="sm">{l.discount_pct}%</Text> : <NumberInput min={0} max={100} decimalScale={2} value={l.discount_pct} onChange={(v) => reprice(l.key, { discount_pct: Number(v) || 0 })} w={80} suffix="%" />}
                </Table.Td>
                <Table.Td>
                  {l.billing_type === 'recurring' && readOnly ? (
                    <Text size="sm">{l.term_months ?? term}</Text>
                  ) : l.billing_type === 'recurring' ? (
                    <NumberInput min={1} max={120} value={l.term_months ?? ''} placeholder={String(term)} onChange={(v) => reprice(l.key, { term_months: v === '' ? null : Number(v) })} w={80} />
                  ) : (
                    <Text size="sm" c="dimmed">
                      —
                    </Text>
                  )}
                </Table.Td>
                <Table.Td ta="right" fw={600}>
                  {money2(lineTotal(l, term), currency)}
                </Table.Td>
                <Table.Td>
                  {!readOnly && (
                    <ActionIcon variant="subtle" color="red" onClick={() => onChange(lines.filter((x) => x.key !== l.key))} aria-label="Remove line">
                      <IconTrash size={16} />
                    </ActionIcon>
                  )}
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </ScrollArea>
      {!readOnly && (
        <Group gap="xs">
          <Button variant="light" size="xs" leftSection={<IconPlus size={14} />} onClick={add}>
            Add line
          </Button>
          <Button variant="subtle" size="xs" leftSection={<IconStack2 size={14} />} onClick={addTotal}>
            Multiple products (total only)
          </Button>
        </Group>
      )}
      {brandId && (
        <NewProductModal
          name={newProduct?.name ?? null}
          brandId={brandId}
          onClose={() => setNewProduct(null)}
          onCreated={(p) => newProduct && setProduct(newProduct.key, p)}
        />
      )}
      <Paper withBorder p="sm" bg="var(--mantine-color-violet-light)">
        <SimpleGrid cols={{ base: 1, xs: 3 }}>
          <Stack gap={0}>
            <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
              Estimated deal value (TCV)
            </Text>
            <Text fw={700} size="xl">
              {money(t.tcv, currency)}
            </Text>
          </Stack>
          <Stack gap={0}>
            <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
              Annual recurring (ARR)
            </Text>
            <Text fw={700} size="xl">
              {money(t.arr, currency)}
            </Text>
          </Stack>
          <Stack gap={0}>
            <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
              One-time / services
            </Text>
            <Text fw={700} size="xl">
              {money(t.oneTime, currency)}
            </Text>
          </Stack>
        </SimpleGrid>
        <Text size="xs" c="dimmed" mt={6}>
          Recurring lines: quantity × monthly unit price × term × (1 − discount). One-time lines: quantity × unit price × (1 − discount). Multiple
          products: the total you enter (a recurring one counts towards ARR over its term).
        </Text>
      </Paper>
    </Stack>
  )
}

/** Product picker with "Multiple products" and, for admins, "add a new product" from what was typed. */
function ProductSelect({
  options,
  value,
  onPick,
  canCreate,
}: {
  options: { value: string; label: string }[]
  value: string | null
  onPick: (v: string | null, search: string) => void
  canCreate: boolean
}) {
  const [search, setSearch] = useState('')
  const q = search.trim()
  const selected = options.find((o) => o.value === value)
  const typing = !!q && q !== selected?.label
  const shown = typing ? options.filter((o) => o.value === MULTIPLE || o.label.toLowerCase().includes(q.toLowerCase())) : options
  const exact = options.some((o) => o.label.toLowerCase().startsWith(`${q.toLowerCase()} (`))
  const data = canCreate && typing && !exact ? [...shown, { value: NEW_PRODUCT, label: `+ Add "${q}" as a new product` }] : shown
  return (
    <Select
      placeholder="Choose a product, Multiple products, or type a custom line below"
      data={data}
      value={value}
      onChange={(v) => onPick(v, q)}
      searchValue={search}
      onSearchChange={setSearch}
      filter={({ options }) => options}
      searchable
      clearable
      nothingFoundMessage="No matching product"
    />
  )
}

function NewProductModal({ name, brandId, onClose, onCreated }: { name: string | null; brandId: number; onClose: () => void; onCreated: (p: Product) => void }) {
  const [v, setV] = useState({ name: '', sku: '', unit: 'host', billing_type: 'recurring' })
  const [shownFor, setShownFor] = useState<string | null>(null)
  if (name !== shownFor) {
    setShownFor(name)
    if (name !== null)
      setV({ name, sku: name.toUpperCase().replace(/[^A-Z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 40), unit: 'host', billing_type: 'recurring' })
  }
  const save = useApiMutation((body: typeof v) => api<Product>('/products', { method: 'POST', body: { ...body, brand_id: brandId } }), {
    invalidate: [['products']],
    success: 'Product created',
    onSuccess: (p) => {
      onCreated(p)
      onClose()
    },
  })
  return (
    <Modal opened={name !== null} onClose={onClose} title="New product">
      <form
        onSubmit={(e) => {
          e.preventDefault()
          save.mutate(v)
        }}
      >
        <Stack>
          <TextInput label="Name" required value={v.name} onChange={(e) => setV({ ...v, name: e.target.value })} data-autofocus />
          <TextInput label="SKU" required maxLength={64} value={v.sku} onChange={(e) => setV({ ...v, sku: e.target.value })} />
          <SimpleGrid cols={2}>
            <Select
              label="Billing"
              data={[
                { value: 'recurring', label: 'Recurring (per month)' },
                { value: 'one_time', label: 'One-time' },
              ]}
              value={v.billing_type}
              onChange={(x) => setV({ ...v, billing_type: x ?? 'recurring' })}
              allowDeselect={false}
            />
            <Select label="Priced per" data={toOptions(UNITS)} value={v.unit} onChange={(x) => setV({ ...v, unit: x ?? 'host' })} allowDeselect={false} />
          </SimpleGrid>
          <Text size="xs" c="dimmed">
            It has no list price yet: enter the unit price on this line, and add it to a price book under Products &amp; pricing.
          </Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" loading={save.isPending}>
              Create product
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  )
}
