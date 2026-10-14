import { ActionIcon, Badge, Button, Group, NumberInput, Paper, Select, SimpleGrid, Stack, Table, Text, TextInput } from '@mantine/core'
import { IconPlus, IconTrash } from '@tabler/icons-react'
import { money, money2, UNITS } from '../labels'
import type { LineItem, PriceBook, Product } from '../types'

export interface DraftLine {
  key: string
  product_id: number | null
  name: string
  billing_type: 'recurring' | 'one_time'
  unit: string | null
  quantity: number
  unit_price: number
  discount_pct: number
  term_months: number | null
}

/** Mirrors backend pricing.py so the user sees totals as they type. */
export function lineTotal(l: DraftLine, defaultTerm: number) {
  const base = l.quantity * l.unit_price * (1 - (l.discount_pct || 0) / 100)
  const total = l.billing_type === 'recurring' ? base * (l.term_months || defaultTerm) : base
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
  billing_type: li.billing_type,
  unit: li.unit ?? null,
  quantity: Number(li.quantity),
  unit_price: Number(li.unit_price),
  discount_pct: Number(li.discount_pct),
  term_months: li.term_months,
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
}: {
  lines: DraftLine[]
  onChange: (l: DraftLine[]) => void
  products: Product[]
  priceBook?: PriceBook
  term: number
  currency: string
  readOnly?: boolean
}) {
  const update = (key: string, patch: Partial<DraftLine>) => onChange(lines.map((l) => (l.key === key ? { ...l, ...patch } : l)))
  const add = () =>
    onChange([
      ...lines,
      { key: `n-${Date.now()}`, product_id: null, name: '', billing_type: 'recurring', unit: null, quantity: 1, unit_price: 0, discount_pct: 0, term_months: null },
    ])
  const pickProduct = (key: string, id: string | null) => {
    const p = products.find((x) => String(x.id) === id)
    if (!p) return update(key, { product_id: null })
    update(key, {
      product_id: p.id,
      name: p.name,
      billing_type: p.billing_type,
      unit: p.unit,
      unit_price: priceFor(p, priceBook) ?? 0,
    })
  }
  const t = totals(lines, term)
  const productOptions = products.filter((p) => p.active).map((p) => {
    const price = priceFor(p, priceBook)
    return { value: String(p.id), label: `${p.name} (${p.sku})${price === null ? ' · no list price' : ''}` }
  })

  return (
    <Stack gap="xs">
      <Table.ScrollContainer minWidth={readOnly ? 560 : 900}>
        <Table verticalSpacing={6}>
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
                    <Select
                      placeholder="Choose a product or type a custom line below"
                      data={productOptions}
                      value={l.product_id ? String(l.product_id) : null}
                      onChange={(v) => pickProduct(l.key, v)}
                      searchable
                      clearable
                    />
                    )}
                    {!l.product_id && !readOnly && (
                      <TextInput placeholder="Custom line name" value={l.name} onChange={(e) => update(l.key, { name: e.target.value })} disabled={readOnly} />
                    )}
                    <Group gap={4}>
                      <Badge size="xs" variant="light" color={l.billing_type === 'recurring' ? 'violet' : 'orange'}>
                        {l.billing_type === 'recurring' ? 'per month' : 'one-time'}
                      </Badge>
                      {l.unit && (
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
                  {readOnly ? <Text size="sm">{l.quantity.toLocaleString('en-US')}</Text> : <NumberInput min={0} decimalScale={2} value={l.quantity} onChange={(v) => update(l.key, { quantity: Number(v) || 0 })} w={90} thousandSeparator />}
                </Table.Td>
                <Table.Td>
                  {readOnly ? <Text size="sm">{money2(l.unit_price, currency)}</Text> : <NumberInput min={0} decimalScale={2} value={l.unit_price} onChange={(v) => update(l.key, { unit_price: Number(v) || 0 })} w={110} prefix={currency === 'EUR' ? '€' : currency === 'USD' ? '$' : `${currency} `} thousandSeparator />}
                </Table.Td>
                <Table.Td>
                  {readOnly ? <Text size="sm">{l.discount_pct}%</Text> : <NumberInput min={0} max={100} decimalScale={2} value={l.discount_pct} onChange={(v) => update(l.key, { discount_pct: Number(v) || 0 })} w={80} suffix="%" />}
                </Table.Td>
                <Table.Td>
                  {l.billing_type === 'recurring' && readOnly ? (
                    <Text size="sm">{l.term_months ?? term}</Text>
                  ) : l.billing_type === 'recurring' ? (
                    <NumberInput min={1} max={120} value={l.term_months ?? ''} placeholder={String(term)} onChange={(v) => update(l.key, { term_months: v === '' ? null : Number(v) })} w={80} />
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
      </Table.ScrollContainer>
      {!readOnly && (
        <Group>
          <Button variant="light" size="xs" leftSection={<IconPlus size={14} />} onClick={add}>
            Add line
          </Button>
        </Group>
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
          Recurring lines: quantity × monthly unit price × term × (1 − discount). One-time lines: quantity × unit price × (1 − discount).
        </Text>
      </Paper>
    </Stack>
  )
}
