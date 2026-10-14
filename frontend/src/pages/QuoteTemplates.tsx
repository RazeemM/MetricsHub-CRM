import {
  Alert,
  Button,
  Card,
  Code,
  ColorInput,
  FileButton,
  Grid,
  Group,
  Image,
  NumberInput,
  ScrollArea,
  SegmentedControl,
  SimpleGrid,
  Stack,
  Switch,
  Table,
  Text,
  Textarea,
  TextInput,
  Title,
} from '@mantine/core'
import { useDebouncedValue } from '@mantine/hooks'
import { modals } from '@mantine/modals'
import { notifications } from '@mantine/notifications'
import { IconEye, IconPhoto, IconRestore, IconTrash } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { api, getToken } from '../api'
import { useAuth } from '../auth'
import { PageHeader } from '../components/common'
import { useApiMutation } from '../hooks'

export interface QuoteTemplate {
  brand_id: number
  brand_name: string
  company_name: string
  address: string | null
  vat_number: string | null
  registration: string | null
  email: string | null
  phone: string | null
  website: string | null
  logo_data_uri: string | null
  logo_height: number
  header_show_name: boolean
  header_bg: string
  header_text_color: string
  accent_color: string
  title: string
  intro_text: string | null
  terms_text: string | null
  payment_terms: string | null
  validity_days: number
  footer_text: string | null
  show_discount: boolean
  show_signature: boolean
}

async function postForBlob(path: string, body: unknown): Promise<Blob> {
  const res = await fetch(`/api${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${getToken()}` },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error('Preview failed: check the highlighted fields')
  return res.blob()
}

function stripMeta({ brand_id: _b, brand_name: _n, ...rest }: QuoteTemplate) {
  return rest
}

export default function QuoteTemplates() {
  const { isAdmin } = useAuth()
  const { data: templates } = useQuery({ queryKey: ['quote-templates'], queryFn: () => api<QuoteTemplate[]>('/quote-templates') })
  const [brandId, setBrandId] = useState<string | null>(null)
  const [draft, setDraft] = useState<QuoteTemplate | null>(null)
  const [previewHtml, setPreviewHtml] = useState('')
  const selected = templates?.find((t) => String(t.brand_id) === brandId) ?? templates?.[0]

  useEffect(() => {
    if (selected) setDraft({ ...selected })
  }, [selected])

  const [debounced] = useDebouncedValue(draft, 400)
  useEffect(() => {
    if (!debounced) return
    let cancelled = false
    postForBlob('/quote-templates/preview', stripMeta(debounced))
      .then((b) => b.text())
      .then((html) => !cancelled && setPreviewHtml(html))
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [debounced])

  const dirty = useMemo(() => JSON.stringify(draft) !== JSON.stringify(selected), [draft, selected])
  const save = useApiMutation(() => api(`/quote-templates/${draft!.brand_id}`, { method: 'PUT', body: stripMeta(draft!) }), {
    invalidate: [['quote-templates']],
    success: 'Quote template saved',
  })
  const reset = useApiMutation(() => api(`/quote-templates/${draft!.brand_id}/reset`, { method: 'POST' }), {
    invalidate: [['quote-templates']],
    success: 'Template reset to defaults',
  })

  if (!draft) return null
  const set = <K extends keyof QuoteTemplate>(k: K) => (v: QuoteTemplate[K]) => setDraft({ ...draft, [k]: v })
  const ro = !isAdmin

  const onLogo = (file: File | null) => {
    if (!file) return
    if (file.size > 500_000) {
      notifications.show({ color: 'red', message: 'Logo must be under 500 KB' })
      return
    }
    const reader = new FileReader()
    reader.onload = () => set('logo_data_uri')(String(reader.result))
    reader.readAsDataURL(file)
  }

  const openPdf = async () => {
    try {
      const blob = await postForBlob('/quote-templates/preview.pdf', stripMeta(draft))
      window.open(URL.createObjectURL(blob), '_blank')
    } catch (e) {
      notifications.show({ color: 'red', message: (e as Error).message })
    }
  }

  return (
    <>
      <PageHeader
        title="Quote templates"
        subtitle="One template per brand. Quotes keep the template as it was when they were generated."
        actions={
          <>
            <Button variant="default" leftSection={<IconEye size={16} />} onClick={openPdf}>
              Preview PDF
            </Button>
            {isAdmin && (
              <>
                <Button
                  variant="subtle"
                  color="gray"
                  leftSection={<IconRestore size={16} />}
                  onClick={() =>
                    modals.openConfirmModal({
                      title: 'Reset to default template?',
                      children: <Text size="sm">All wording, colours and the logo for {draft.brand_name} go back to the defaults.</Text>,
                      labels: { confirm: 'Reset', cancel: 'Cancel' },
                      onConfirm: () => reset.mutate(undefined),
                    })
                  }
                >
                  Reset
                </Button>
                <Button onClick={() => save.mutate(undefined)} loading={save.isPending} disabled={!dirty}>
                  Save template
                </Button>
              </>
            )}
          </>
        }
      />
      <SegmentedControl
        mb="md"
        data={(templates ?? []).map((t) => ({ value: String(t.brand_id), label: t.brand_name }))}
        value={String(draft.brand_id)}
        onChange={(v) => {
          if (dirty && !window.confirm('Discard unsaved changes?')) return
          setBrandId(v)
        }}
      />
      {ro && (
        <Alert mb="md" variant="light">
          Only administrators can edit templates.
        </Alert>
      )}
      <Grid>
        <Grid.Col span={{ base: 12, lg: 5 }}>
          <Stack>
            <Card withBorder>
              <Title order={5} mb="sm">
                Company &amp; branding
              </Title>
              <Stack gap="sm">
                <Group align="flex-end">
                  <div style={{ background: draft.header_bg, padding: 10, borderRadius: 6, minWidth: 120, minHeight: 56, display: 'flex', alignItems: 'center' }}>
                    {draft.logo_data_uri ? <Image src={draft.logo_data_uri} h={draft.logo_height} w="auto" fit="contain" alt="Logo" /> : <Text c={draft.header_text_color} size="sm">No logo</Text>}
                  </div>
                  {!ro && (
                    <>
                      <FileButton onChange={onLogo} accept="image/png,image/jpeg,image/webp,image/svg+xml">
                        {(props) => (
                          <Button {...props} variant="default" leftSection={<IconPhoto size={16} />}>
                            Upload logo
                          </Button>
                        )}
                      </FileButton>
                      {draft.logo_data_uri && (
                        <Button variant="subtle" color="red" leftSection={<IconTrash size={16} />} onClick={() => set('logo_data_uri')(null)}>
                          Remove
                        </Button>
                      )}
                    </>
                  )}
                </Group>
                <Text size="xs" c="dimmed">
                  PNG, JPEG, WebP or SVG under 500 KB. Use a high-resolution or SVG logo for sharp printing; a white logo needs a dark header colour.
                </Text>
                <SimpleGrid cols={2}>
                  <NumberInput label="Logo height (px)" min={16} max={120} value={draft.logo_height} onChange={(v) => set('logo_height')(Number(v) || 36)} disabled={ro} />
                  <Switch mt="xl" label="Show company name in header" checked={draft.header_show_name} onChange={(e) => set('header_show_name')(e.currentTarget.checked)} disabled={ro} />
                  <ColorInput label="Header background" value={draft.header_bg} onChange={set('header_bg')} format="hex" disabled={ro} />
                  <ColorInput label="Header text" value={draft.header_text_color} onChange={set('header_text_color')} format="hex" disabled={ro} />
                  <ColorInput label="Accent colour" value={draft.accent_color} onChange={set('accent_color')} format="hex" disabled={ro} />
                  <TextInput label="Document title" value={draft.title} onChange={(e) => set('title')(e.target.value)} disabled={ro} />
                </SimpleGrid>
                <TextInput label="Company name" value={draft.company_name} onChange={(e) => set('company_name')(e.target.value)} disabled={ro} />
                <Textarea label="Address" autosize minRows={3} value={draft.address ?? ''} onChange={(e) => set('address')(e.target.value)} disabled={ro} />
                <SimpleGrid cols={2}>
                  <TextInput label="VAT number" value={draft.vat_number ?? ''} onChange={(e) => set('vat_number')(e.target.value)} disabled={ro} />
                  <TextInput label="Registration (RCS, SIRET…)" value={draft.registration ?? ''} onChange={(e) => set('registration')(e.target.value)} disabled={ro} />
                  <TextInput label="Email" value={draft.email ?? ''} onChange={(e) => set('email')(e.target.value)} disabled={ro} />
                  <TextInput label="Phone" value={draft.phone ?? ''} onChange={(e) => set('phone')(e.target.value)} disabled={ro} />
                  <TextInput label="Website" value={draft.website ?? ''} onChange={(e) => set('website')(e.target.value)} disabled={ro} />
                  <NumberInput label="Default validity (days)" min={1} max={365} value={draft.validity_days} onChange={(v) => set('validity_days')(Number(v) || 30)} disabled={ro} />
                </SimpleGrid>
              </Stack>
            </Card>
            <Card withBorder>
              <Title order={5} mb="sm">
                Wording
              </Title>
              <Stack gap="sm">
                <Textarea label="Introduction" autosize minRows={3} value={draft.intro_text ?? ''} onChange={(e) => set('intro_text')(e.target.value)} disabled={ro} />
                <TextInput label="Payment terms" value={draft.payment_terms ?? ''} onChange={(e) => set('payment_terms')(e.target.value)} disabled={ro} />
                <Textarea label="Terms & conditions" autosize minRows={6} maxRows={18} value={draft.terms_text ?? ''} onChange={(e) => set('terms_text')(e.target.value)} disabled={ro} />
                <Textarea label="Footer" autosize minRows={1} value={draft.footer_text ?? ''} onChange={(e) => set('footer_text')(e.target.value)} disabled={ro} />
                <Group>
                  <Switch label="Discount column (when a line has a discount)" checked={draft.show_discount} onChange={(e) => set('show_discount')(e.currentTarget.checked)} disabled={ro} />
                  <Switch label="Signature block" checked={draft.show_signature} onChange={(e) => set('show_signature')(e.currentTarget.checked)} disabled={ro} />
                </Group>
                <Card withBorder bg="var(--mantine-color-default-hover)" p="xs">
                  <Text size="xs" fw={600} mb={4}>
                    Placeholders and formatting
                  </Text>
                  <Table fz="xs" verticalSpacing={2}>
                    <Table.Tbody>
                      {[
                        ['{customer}', 'Customer account'],
                        ['{contact}', 'Primary contact'],
                        ['{owner}', 'Opportunity owner'],
                        ['{company}', 'Your company name'],
                        ['{quote_number}', 'Quote number'],
                        ['{valid_until}', 'Expiry date'],
                        ['{term_months}', 'Contract months'],
                        ['{currency}', 'Currency'],
                      ].map(([k, v]) => (
                        <Table.Tr key={k}>
                          <Table.Td>
                            <Code>{k}</Code>
                          </Table.Td>
                          <Table.Td>{v}</Table.Td>
                        </Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                  <Text size="xs" c="dimmed" mt={4}>
                    Blank line = new paragraph · lines starting with “- ” = bullet list · **text** = bold
                  </Text>
                </Card>
              </Stack>
            </Card>
          </Stack>
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 7 }}>
          <Card withBorder p={0} style={{ position: 'sticky', top: 72 }}>
            <Group justify="space-between" px="sm" py={6}>
              <Text size="sm" fw={600}>
                Live preview (sample data)
              </Text>
              {dirty && (
                <Text size="xs" c="orange">
                  Unsaved changes
                </Text>
              )}
            </Group>
            <ScrollArea h="calc(100vh - 170px)" bg="gray.3">
              <iframe
                title="Quote preview"
                srcDoc={previewHtml}
                sandbox=""
                style={{ width: 'calc(100% - 24px)', maxWidth: '210mm', height: 1180, border: 0, background: 'white', display: 'block', margin: '12px auto', boxShadow: '0 2px 12px rgba(0,0,0,.15)' }}
              />
            </ScrollArea>
          </Card>
        </Grid.Col>
      </Grid>
    </>
  )
}
