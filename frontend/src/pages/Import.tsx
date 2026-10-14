import { Alert, Badge, Button, Card, Group, Select, SegmentedControl, SimpleGrid, Stack, Stepper, Table, Text, Title } from '@mantine/core'
import { Dropzone } from '@mantine/dropzone'
import { notifications } from '@mantine/notifications'
import { IconDownload, IconFileSpreadsheet, IconUpload } from '@tabler/icons-react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, download } from '../api'
import { useAuth } from '../auth'
import { PageHeader, UserPicker } from '../components/common'
import { FreshsalesMigration } from '../components/FreshsalesMigration'
import { useBrands } from '../hooks'
import { ACCOUNT_TYPES, CONTACT_ROLES, LEAD_SOURCES, LIFECYCLES, toOptions } from '../labels'

interface Preview {
  headers: string[]
  sample: Record<string, string>[]
  total_rows: number
  suggested_mapping: Record<string, string | null>
  fields: string[]
}
interface Result {
  id: number
  entity: string
  filename: string
  total: number
  created: number
  updated: number
  skipped: number
  errors: { row: number; error: string }[]
}

const FIELD_LABELS: Record<string, string> = {
  first_name: 'First name',
  last_name: 'Last name',
  full_name: 'Full name (split automatically)',
  email: 'Email',
  phone: 'Phone',
  mobile: 'Mobile',
  job_title: 'Job title',
  company: 'Company / account',
  website: 'Website / domain',
  country: 'Country',
  linkedin: 'LinkedIn',
  lifecycle: 'Lifecycle',
  source: 'Lead source',
  contact_role: 'Contact role',
  brand: 'Brand',
  consent_marketing: 'Marketing consent',
  notes: 'Notes',
  name: 'Account name',
  account_type: 'Account type',
  industry: 'Industry',
  region: 'Region',
  city: 'City',
  address: 'Address',
  vat_number: 'VAT number',
}

export default function ImportPage() {
  const qc = useQueryClient()
  const { canWrite, isAdmin } = useAuth()
  const { data: brands } = useBrands()
  const [step, setStep] = useState(0)
  const [entity, setEntity] = useState<'contacts' | 'accounts'>('contacts')
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [mapping, setMapping] = useState<Record<string, string | null>>({})
  const [opts, setOpts] = useState({
    on_duplicate: 'update',
    default_lifecycle: 'lead',
    default_source: 'import',
    default_role: 'customer_contact',
    default_account_type: 'prospect',
    brand_id: null as string | null,
    owner_id: null as number | null,
  })
  const [result, setResult] = useState<Result | null>(null)
  const [busy, setBusy] = useState(false)
  const { data: history } = useQuery({ queryKey: ['imports'], queryFn: () => api<Result[]>('/imports') })

  const upload = async (f: File) => {
    setFile(f)
    setBusy(true)
    try {
      const form = new FormData()
      form.append('entity', entity)
      form.append('file', f)
      const p = await api<Preview>('/imports/preview', { method: 'POST', form })
      setPreview(p)
      setMapping(p.suggested_mapping)
      setStep(1)
    } catch (e) {
      notifications.show({ color: 'red', message: (e as Error).message })
    } finally {
      setBusy(false)
    }
  }

  const commit = async () => {
    if (!file) return
    setBusy(true)
    try {
      const form = new FormData()
      form.append('entity', entity)
      form.append('file', file)
      form.append('mapping', JSON.stringify(mapping))
      Object.entries(opts).forEach(([k, v]) => {
        if (v !== null && v !== '') form.append(k, String(v))
      })
      const r = await api<Result>('/imports/commit', { method: 'POST', form })
      setResult(r)
      setStep(2)
      qc.invalidateQueries({ queryKey: ['contacts'] })
      qc.invalidateQueries({ queryKey: ['accounts'] })
      qc.invalidateQueries({ queryKey: ['imports'] })
    } catch (e) {
      notifications.show({ color: 'red', message: (e as Error).message })
    } finally {
      setBusy(false)
    }
  }

  const restart = () => {
    setStep(0)
    setFile(null)
    setPreview(null)
    setResult(null)
  }
  const mappedFields = Object.entries(mapping).filter(([, v]) => v)
  const missingKey = entity === 'contacts' ? !mapping.email && !mapping.full_name && !mapping.first_name && !mapping.last_name : !mapping.name

  return (
    <>
      <PageHeader
        title="Import / export"
        subtitle="Load leads and accounts from Excel or CSV; export any list"
        actions={
          <>
            <Button variant="default" leftSection={<IconDownload size={16} />} onClick={() => download('/export/contacts')}>
              Contacts
            </Button>
            <Button variant="default" leftSection={<IconDownload size={16} />} onClick={() => download('/export/accounts')}>
              Accounts
            </Button>
            <Button variant="default" leftSection={<IconDownload size={16} />} onClick={() => download('/export/opportunities', { status: undefined })}>
              Opportunities
            </Button>
          </>
        }
      />
      {isAdmin && <FreshsalesMigration />}
      {canWrite && (
        <Card withBorder mb="md">
          <Stepper active={step} size="sm" mb="lg">
            <Stepper.Step label="Upload" description=".xlsx or .csv" />
            <Stepper.Step label="Map columns" description="Match file columns to CRM fields" />
            <Stepper.Step label="Done" />
          </Stepper>

          {step === 0 && (
            <Stack>
              <SegmentedControl
                value={entity}
                onChange={(v) => setEntity(v as 'contacts' | 'accounts')}
                data={[
                  { value: 'contacts', label: 'Leads / contacts' },
                  { value: 'accounts', label: 'Accounts' },
                ]}
                w={320}
              />
              <Dropzone
                onDrop={(files) => files[0] && upload(files[0])}
                loading={busy}
                multiple={false}
                maxSize={20 * 1024 * 1024}
                accept={{
                  'text/csv': ['.csv'],
                  'text/plain': ['.txt'],
                  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
                  'application/vnd.ms-excel': ['.csv'],
                }}
              >
                <Group justify="center" gap="md" mih={140} style={{ pointerEvents: 'none' }}>
                  <Dropzone.Accept>
                    <IconUpload size={40} />
                  </Dropzone.Accept>
                  <Dropzone.Idle>
                    <IconFileSpreadsheet size={40} stroke={1.5} />
                  </Dropzone.Idle>
                  <div>
                    <Text size="lg">Drop an Excel or CSV file here, or click to choose</Text>
                    <Text size="sm" c="dimmed">
                      First row must contain column headers. Up to 50,000 rows, 20 MB.
                    </Text>
                  </div>
                </Group>
              </Dropzone>
            </Stack>
          )}

          {step === 1 && preview && (
            <Stack>
              <Text size="sm">
                <b>{file?.name}</b> · {preview.total_rows} rows · {preview.headers.length} columns
              </Text>
              <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }}>
                {preview.fields.map((field) => (
                  <Select
                    key={field}
                    label={FIELD_LABELS[field] ?? field}
                    placeholder="— not imported —"
                    data={preview.headers}
                    value={mapping[field] ?? null}
                    onChange={(v) => setMapping({ ...mapping, [field]: v })}
                    clearable
                  />
                ))}
              </SimpleGrid>
              <Title order={6} mt="sm">
                Options
              </Title>
              <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }}>
                <Select
                  label="When a record already exists"
                  description={entity === 'contacts' ? 'Matched by email' : 'Matched by domain, then name'}
                  data={[
                    { value: 'update', label: 'Update it with non-empty values' },
                    { value: 'skip', label: 'Skip the row' },
                  ]}
                  value={opts.on_duplicate}
                  onChange={(v) => setOpts({ ...opts, on_duplicate: v ?? 'update' })}
                />
                {entity === 'contacts' && (
                  <>
                    <Select label="Default lifecycle" data={toOptions(LIFECYCLES)} value={opts.default_lifecycle} onChange={(v) => setOpts({ ...opts, default_lifecycle: v ?? 'lead' })} />
                    <Select label="Default source" data={toOptions(LEAD_SOURCES)} value={opts.default_source} onChange={(v) => setOpts({ ...opts, default_source: v ?? 'import' })} />
                    <Select label="Default contact role" data={toOptions(CONTACT_ROLES)} value={opts.default_role} onChange={(v) => setOpts({ ...opts, default_role: v ?? 'customer_contact' })} />
                    <Select
                      label="Brand interest"
                      data={(brands ?? []).map((b) => ({ value: String(b.id), label: b.name }))}
                      value={opts.brand_id}
                      onChange={(v) => setOpts({ ...opts, brand_id: v })}
                      clearable
                    />
                  </>
                )}
                <Select
                  label="Type for new accounts"
                  data={toOptions(ACCOUNT_TYPES)}
                  value={opts.default_account_type}
                  onChange={(v) => setOpts({ ...opts, default_account_type: v ?? 'prospect' })}
                />
                <UserPicker label="Owner" placeholder="Me" value={opts.owner_id} onChange={(v) => setOpts({ ...opts, owner_id: v })} />
              </SimpleGrid>
              <Title order={6} mt="sm">
                Preview (first rows, mapped columns)
              </Title>
              <Table.ScrollContainer minWidth={600}>
                <Table striped fz="xs">
                  <Table.Thead>
                    <Table.Tr>
                      {mappedFields.map(([f]) => (
                        <Table.Th key={f}>{FIELD_LABELS[f] ?? f}</Table.Th>
                      ))}
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {preview.sample.slice(0, 5).map((row, i) => (
                      <Table.Tr key={i}>
                        {mappedFields.map(([f, col]) => (
                          <Table.Td key={f}>{row[col as string]}</Table.Td>
                        ))}
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </Table.ScrollContainer>
              {missingKey && (
                <Alert color="orange" variant="light">
                  {entity === 'contacts' ? 'Map at least an email or a name column.' : 'Map the account name column.'}
                </Alert>
              )}
              <Group justify="space-between">
                <Button variant="default" onClick={restart}>
                  Back
                </Button>
                <Button onClick={commit} loading={busy} disabled={missingKey}>
                  Import {preview.total_rows} rows
                </Button>
              </Group>
            </Stack>
          )}

          {step === 2 && result && (
            <Stack>
              <Group>
                <Badge size="lg" color="green" variant="light">
                  {result.created} created
                </Badge>
                <Badge size="lg" color="blue" variant="light">
                  {result.updated} updated
                </Badge>
                <Badge size="lg" color={result.skipped ? 'orange' : 'gray'} variant="light">
                  {result.skipped} skipped
                </Badge>
              </Group>
              {result.errors.length > 0 && (
                <Table fz="sm">
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Row</Table.Th>
                      <Table.Th>Problem</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {result.errors.map((e) => (
                      <Table.Tr key={e.row}>
                        <Table.Td>{e.row}</Table.Td>
                        <Table.Td>{e.error}</Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              )}
              <Group>
                <Button onClick={restart}>Import another file</Button>
              </Group>
            </Stack>
          )}
        </Card>
      )}
      <Card withBorder>
        <Title order={5} mb="sm">
          Recent imports
        </Title>
        <Table fz="sm">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>File</Table.Th>
              <Table.Th>Type</Table.Th>
              <Table.Th>Rows</Table.Th>
              <Table.Th>Created</Table.Th>
              <Table.Th>Updated</Table.Th>
              <Table.Th>Skipped</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {history?.map((h) => (
              <Table.Tr key={h.id}>
                <Table.Td>{h.filename}</Table.Td>
                <Table.Td>{h.entity}</Table.Td>
                <Table.Td>{h.total}</Table.Td>
                <Table.Td>{h.created}</Table.Td>
                <Table.Td>{h.updated}</Table.Td>
                <Table.Td>{h.skipped}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
        {!history?.length && (
          <Text size="sm" c="dimmed">
            No imports yet.
          </Text>
        )}
      </Card>
    </>
  )
}
