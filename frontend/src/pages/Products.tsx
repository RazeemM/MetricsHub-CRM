import { Alert, Badge, Button, Card, Checkbox, Group, Modal, NumberInput, Select, SimpleGrid, Stack, Table, Tabs, Text, Textarea, TextInput } from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { IconPlus } from '@tabler/icons-react'
import { useEffect, useState } from 'react'
import { api } from '../api'
import { useAuth } from '../auth'
import { PageHeader } from '../components/common'
import { useApiMutation, useBrands, usePriceBooks, useProducts } from '../hooks'
import { CHANNELS, money2, toOptions, UNITS } from '../labels'
import type { PriceBook, Product } from '../types'

function ProductModal({ opened, onClose, product }: { opened: boolean; onClose: () => void; product: Product | null }) {
  const { data: brands } = useBrands()
  const [v, setV] = useState<Partial<Product>>({})
  useEffect(() => {
    if (opened) setV(product ? { ...product } : { unit: 'host', billing_type: 'recurring', active: true, brand_id: brands?.[0]?.id })
  }, [opened, product, brands])
  const save = useApiMutation(
    (body: Partial<Product>) => (product ? api(`/products/${product.id}`, { method: 'PATCH', body }) : api('/products', { method: 'POST', body })),
    { invalidate: [['products']], success: 'Product saved', onSuccess: onClose },
  )
  return (
    <Modal opened={opened} onClose={onClose} title={product ? 'Edit product' : 'New product'} size="lg">
      <form
        onSubmit={(e) => {
          e.preventDefault()
          const { brand_id, sku, name, description, unit, billing_type, active } = v
          save.mutate({ brand_id, sku, name, description, unit, billing_type, active })
        }}
      >
        <Stack>
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <Select
              label="Brand"
              required
              data={(brands ?? []).map((b) => ({ value: String(b.id), label: b.name }))}
              value={v.brand_id ? String(v.brand_id) : null}
              onChange={(x) => setV({ ...v, brand_id: Number(x) })}
            />
            <TextInput label="SKU" required value={v.sku ?? ''} onChange={(e) => setV({ ...v, sku: e.target.value })} />
            <TextInput label="Name" required value={v.name ?? ''} onChange={(e) => setV({ ...v, name: e.target.value })} />
            <Select label="Licensing unit" data={toOptions(UNITS)} value={v.unit ?? 'host'} onChange={(x) => setV({ ...v, unit: x ?? 'host' })} />
            <Select
              label="Billing"
              data={[
                { value: 'recurring', label: 'Recurring (price per month)' },
                { value: 'one_time', label: 'One-time' },
              ]}
              value={v.billing_type ?? 'recurring'}
              onChange={(x) => setV({ ...v, billing_type: (x ?? 'recurring') as Product['billing_type'] })}
            />
            <Checkbox label="Active" mt="xl" checked={v.active ?? true} onChange={(e) => setV({ ...v, active: e.currentTarget.checked })} />
          </SimpleGrid>
          <Textarea label="Description (shown on quotes)" autosize minRows={2} value={v.description ?? ''} onChange={(e) => setV({ ...v, description: e.target.value })} />
          <Group justify="flex-end">
            <Button type="submit" loading={save.isPending}>
              Save
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  )
}

function PriceBookEditor({ book, products, isAdmin }: { book: PriceBook; products: Product[]; isAdmin: boolean }) {
  const [prices, setPrices] = useState<Record<number, number | ''>>({})
  useEffect(() => {
    const m: Record<number, number | ''> = {}
    book.entries.forEach((e) => (m[e.product_id] = Number(e.unit_price)))
    setPrices(m)
  }, [book])
  const save = useApiMutation(
    () =>
      api(`/price-books/${book.id}`, {
        method: 'PATCH',
        body: {
          entries: Object.entries(prices)
            .filter(([, p]) => p !== '' && p !== undefined)
            .map(([pid, p]) => ({ product_id: Number(pid), unit_price: p })),
        },
      }),
    { invalidate: [['price-books'], ['products']], success: 'Prices saved' },
  )
  const list = products.filter((p) => !book.brand_id || p.brand_id === book.brand_id)
  return (
    <Stack>
      <Table>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Product</Table.Th>
            <Table.Th>Unit</Table.Th>
            <Table.Th>Billing</Table.Th>
            <Table.Th>Unit price ({book.currency})</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {list.map((p) => (
            <Table.Tr key={p.id}>
              <Table.Td>
                {p.name}{' '}
                <Text span size="xs" c="dimmed">
                  {p.sku}
                </Text>
              </Table.Td>
              <Table.Td>{UNITS[p.unit]}</Table.Td>
              <Table.Td>{p.billing_type === 'recurring' ? 'per month' : 'one-time'}</Table.Td>
              <Table.Td>
                {isAdmin ? (
                  <NumberInput
                    w={140}
                    min={0}
                    decimalScale={2}
                    placeholder="no price"
                    value={prices[p.id] ?? ''}
                    onChange={(v) => setPrices({ ...prices, [p.id]: v === '' ? '' : Number(v) })}
                  />
                ) : prices[p.id] !== undefined && prices[p.id] !== '' ? (
                  money2(prices[p.id] as number, book.currency)
                ) : (
                  '—'
                )}
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      {isAdmin && (
        <Group justify="flex-end">
          <Button onClick={() => save.mutate(undefined)} loading={save.isPending}>
            Save prices
          </Button>
        </Group>
      )}
    </Stack>
  )
}

function NewPriceBookModal({ opened, onClose }: { opened: boolean; onClose: () => void }) {
  const { data: brands } = useBrands()
  const [v, setV] = useState({ name: '', brand_id: null as number | null, currency: 'USD', channel: 'direct', is_default: false })
  const save = useApiMutation((body: typeof v) => api('/price-books', { method: 'POST', body }), {
    invalidate: [['price-books']],
    success: 'Price book created',
    onSuccess: onClose,
  })
  return (
    <Modal opened={opened} onClose={onClose} title="New price book">
      <Stack>
        <TextInput label="Name" required value={v.name} onChange={(e) => setV({ ...v, name: e.target.value })} />
        <Select label="Brand" data={(brands ?? []).map((b) => ({ value: String(b.id), label: b.name }))} value={v.brand_id ? String(v.brand_id) : null} onChange={(x) => setV({ ...v, brand_id: x ? Number(x) : null })} />
        <Select label="Currency" data={['USD', 'EUR', 'GBP', 'CHF', 'AED', 'INR', 'SGD', 'AUD', 'CAD']} value={v.currency} onChange={(x) => setV({ ...v, currency: x ?? 'USD' })} />
        <Select label="Channel" data={toOptions(CHANNELS)} value={v.channel} onChange={(x) => setV({ ...v, channel: x ?? 'direct' })} />
        <Checkbox label="Default for this brand" checked={v.is_default} onChange={(e) => setV({ ...v, is_default: e.currentTarget.checked })} />
        <Group justify="flex-end">
          <Button disabled={!v.name} loading={save.isPending} onClick={() => save.mutate(v)}>
            Create
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}

export default function Products() {
  const { isAdmin } = useAuth()
  const { data: brands } = useBrands()
  const { data: products } = useProducts()
  const { data: books } = usePriceBooks()
  const [editing, setEditing] = useState<Product | null>(null)
  const [opened, modal] = useDisclosure()
  const [pbOpen, pbModal] = useDisclosure()
  const [bookId, setBookId] = useState<string | null>(null)
  const book = books?.find((b) => String(b.id) === bookId) ?? books?.[0]
  const brandName = (id: number | null) => brands?.find((b) => b.id === id)?.name ?? 'All brands'

  return (
    <>
      <PageHeader title="Products & pricing" subtitle="Catalog and price books used to value opportunities" />
      <Alert variant="light" color="orange" mb="md" title="Placeholder prices">
        Apart from MetricsHub Enterprise ($15/host/month) and the two Sentry bundles, prices are placeholders. Admins can change them under
        Price books; new opportunities pick up the new prices, and existing ones keep theirs.
      </Alert>
      <Tabs defaultValue="products">
        <Tabs.List>
          <Tabs.Tab value="products">Products</Tabs.Tab>
          <Tabs.Tab value="books">Price books</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="products" pt="md">
          <Card withBorder>
            {isAdmin && (
              <Group justify="flex-end" mb="sm">
                <Button
                  leftSection={<IconPlus size={16} />}
                  onClick={() => {
                    setEditing(null)
                    modal.open()
                  }}
                >
                  New product
                </Button>
              </Group>
            )}
            <Table.ScrollContainer minWidth={800}>
              <Table highlightOnHover>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>SKU</Table.Th>
                    <Table.Th>Name</Table.Th>
                    <Table.Th>Brand</Table.Th>
                    <Table.Th>Unit</Table.Th>
                    <Table.Th>Billing</Table.Th>
                    <Table.Th>List prices</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {products?.map((p) => (
                    <Table.Tr
                      key={p.id}
                      className={isAdmin ? 'clickable-row' : undefined}
                      onClick={() => {
                        if (!isAdmin) return
                        setEditing(p)
                        modal.open()
                      }}
                      opacity={p.active ? 1 : 0.5}
                    >
                      <Table.Td ff="monospace" fz="sm">
                        {p.sku}
                      </Table.Td>
                      <Table.Td fw={500}>{p.name}</Table.Td>
                      <Table.Td>{brandName(p.brand_id)}</Table.Td>
                      <Table.Td>{UNITS[p.unit]}</Table.Td>
                      <Table.Td>{p.billing_type === 'recurring' ? 'per month' : 'one-time'}</Table.Td>
                      <Table.Td>
                        <Group gap={4}>
                          {p.prices.length
                            ? p.prices.map((pr) => (
                                <Badge key={pr.price_book_id} variant="light" tt="none">
                                  {money2(pr.unit_price, pr.currency)} · {pr.price_book}
                                </Badge>
                              ))
                            : <Text size="sm" c="dimmed">set per deal</Text>}
                        </Group>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          </Card>
        </Tabs.Panel>
        <Tabs.Panel value="books" pt="md">
          <Card withBorder>
            <Group justify="space-between" mb="sm">
              <Select
                data={(books ?? []).map((b) => ({ value: String(b.id), label: `${b.name} · ${b.currency} · ${CHANNELS[b.channel]}${b.is_default ? ' (default)' : ''}` }))}
                value={book ? String(book.id) : null}
                onChange={setBookId}
                w={420}
                allowDeselect={false}
              />
              {isAdmin && (
                <Button variant="light" leftSection={<IconPlus size={16} />} onClick={pbModal.open}>
                  New price book
                </Button>
              )}
            </Group>
            {book && (
              <>
                <Text size="sm" c="dimmed" mb="sm">
                  {brandName(book.brand_id)} · recurring prices are per unit per month.
                </Text>
                <PriceBookEditor book={book} products={products ?? []} isAdmin={isAdmin} />
              </>
            )}
          </Card>
        </Tabs.Panel>
      </Tabs>
      <ProductModal opened={opened} onClose={modal.close} product={editing} />
      <NewPriceBookModal opened={pbOpen} onClose={pbModal.close} />
    </>
  )
}
