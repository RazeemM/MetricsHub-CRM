import { Alert, Badge, Button, Card, Group, List, Select, SimpleGrid, Stack, Table, Text, TextInput, Title } from '@mantine/core'
import { Dropzone } from '@mantine/dropzone'
import { modals } from '@mantine/modals'
import { notifications } from '@mantine/notifications'
import { IconAlertTriangle, IconCloudUpload, IconX } from '@tabler/icons-react'
import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api'
import { usePipelines } from '../hooks'

interface Report {
  dry_run: boolean
  files: { name: string; rows: number }[]
  counts: Record<'accounts' | 'contacts' | 'deals', Record<string, number>>
  stage_mapping: Record<string, string>
  unmapped_stages: Record<string, number>
  unmatched_owners: Record<string, number>
  brands: Record<string, number>
  referring_platforms: Record<string, number>
  open_pipeline_by_currency: Record<string, string>
  warnings: string[]
}

export function FreshsalesMigration() {
  const qc = useQueryClient()
  const { data: pipelines } = usePipelines()
  const [files, setFiles] = useState<File[]>([])
  const [brand, setBrand] = useState('METRICSHUB')
  const [currency, setCurrency] = useState('USD')
  const [stageMap, setStageMap] = useState<Record<string, string>>({})
  const [report, setReport] = useState<Report | null>(null)
  const [busy, setBusy] = useState(false)
  const stageOptions = (pipelines ?? []).map((p) => ({ group: p.name, items: p.stages.map((s) => s.name) }))

  const run = async (commit: boolean) => {
    setBusy(true)
    try {
      const form = new FormData()
      files.forEach((f) => form.append('files', f))
      form.append('commit', String(commit))
      form.append('default_brand', brand)
      form.append('default_currency', currency)
      form.append('stage_map', JSON.stringify(stageMap))
      const r = await api<Report>('/migrations/freshsales', { method: 'POST', form })
      setReport(r)
      if (commit) {
        notifications.show({ color: 'green', message: 'Freshsales data imported' })
        ;['accounts', 'contacts', 'opportunities', 'board', 'dashboard', 'imports'].forEach((k) => qc.invalidateQueries({ queryKey: [k] }))
      }
    } catch (e) {
      notifications.show({ color: 'red', message: (e as Error).message })
    } finally {
      setBusy(false)
    }
  }

  const fmt = (c: Record<string, number>) =>
    Object.entries(c)
      .map(([k, v]) => `${v} ${k}`)
      .join(' · ') || '—'

  return (
    <Card withBorder mb="md">
      <Title order={5}>Migrate from Freshsales</Title>
      <Text size="sm" c="dimmed" mb="sm">
        In Freshsales go to <b>Admin settings → Data management → Export</b>, export Accounts, Contacts and Deals (all fields), then drop the files
        here. Always run a dry run first: it shows exactly what would change without writing anything. Re-running later updates the same records
        instead of duplicating them.
      </Text>
      <Stack>
        <Dropzone
          onDrop={(f) => {
            setFiles((prev) => [...prev.filter((p) => !f.some((x) => x.name === p.name)), ...f])
            setReport(null)
          }}
          maxSize={20 * 1024 * 1024}
          accept={{
            'text/csv': ['.csv'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
            'application/vnd.ms-excel': ['.csv'],
          }}
        >
          <Group justify="center" gap="sm" mih={70} style={{ pointerEvents: 'none' }}>
            <IconCloudUpload size={28} stroke={1.5} />
            <Text size="sm">Drop the Freshsales export files (accounts, contacts, deals)</Text>
          </Group>
        </Dropzone>
        {files.length > 0 && (
          <Group gap="xs">
            {files.map((f) => (
              <Badge
                key={f.name}
                variant="light"
                tt="none"
                rightSection={<IconX size={12} style={{ cursor: 'pointer' }} onClick={() => setFiles(files.filter((x) => x !== f))} />}
              >
                {f.name}
              </Badge>
            ))}
          </Group>
        )}
        <SimpleGrid cols={{ base: 1, sm: 3 }}>
          <Select
            label="Brand when a deal doesn't say"
            description="Deals mentioning Sentry, BMC, Helix or a KM go to Sentry automatically"
            data={[
              { value: 'METRICSHUB', label: 'MetricsHub' },
              { value: 'SENTRY', label: 'Sentry Software' },
            ]}
            value={brand}
            onChange={(v) => setBrand(v ?? 'METRICSHUB')}
            allowDeselect={false}
          />
          <TextInput label="Currency when missing" description="ISO code" value={currency} onChange={(e) => setCurrency(e.target.value.toUpperCase())} maxLength={3} />
        </SimpleGrid>
        <Group>
          <Button variant="default" disabled={!files.length} loading={busy} onClick={() => run(false)}>
            Dry run
          </Button>
          <Button
            disabled={!report || !report.dry_run}
            loading={busy}
            onClick={() =>
              modals.openConfirmModal({
                title: 'Import into the CRM?',
                children: <Text size="sm">This writes the records shown in the dry run. Running it again later updates them rather than duplicating.</Text>,
                labels: { confirm: 'Import', cancel: 'Cancel' },
                onConfirm: () => run(true),
              })
            }
          >
            Import for real
          </Button>
        </Group>

        {report && (
          <Stack gap="sm">
            <Alert color={report.dry_run ? 'blue' : 'green'} variant="light" title={report.dry_run ? 'Dry run: nothing written yet' : 'Import complete'}>
              <Text size="sm">Files: {report.files.map((f) => `${f.name} (${f.rows} rows)`).join(', ')}</Text>
              <Text size="sm">Accounts: {fmt(report.counts.accounts)}</Text>
              <Text size="sm">Contacts: {fmt(report.counts.contacts)}</Text>
              <Text size="sm">Deals: {fmt(report.counts.deals)}</Text>
              <Text size="sm">
                Brands: {fmt(report.brands)} · Referring platforms: {fmt(report.referring_platforms)}
              </Text>
              <Text size="sm">
                Open pipeline:{' '}
                {Object.entries(report.open_pipeline_by_currency)
                  .map(([c, v]) => `${c} ${Number(v).toLocaleString('en-US')}`)
                  .join(' · ') || '—'}
              </Text>
            </Alert>

            {Object.keys(report.stage_mapping).length > 0 && (
              <>
                <Text size="sm" fw={600}>
                  Deal stage mapping (change any row, then dry-run again)
                </Text>
                <Table fz="sm" withTableBorder>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Freshsales stage</Table.Th>
                      <Table.Th>CRM stage</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {Object.entries(report.stage_mapping).map(([fs, crm]) => (
                      <Table.Tr key={fs}>
                        <Table.Td>
                          {fs}{' '}
                          {report.unmapped_stages[fs] && (
                            <Badge color="orange" size="xs" leftSection={<IconAlertTriangle size={10} />}>
                              not recognised
                            </Badge>
                          )}
                        </Table.Td>
                        <Table.Td>
                          <Select size="xs" w={240} data={stageOptions} value={stageMap[fs] ?? crm} onChange={(v) => v && setStageMap({ ...stageMap, [fs]: v })} />
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </>
            )}

            {Object.keys(report.unmatched_owners).length > 0 && (
              <Alert color="orange" variant="light" title="Owners not found in the CRM">
                <Text size="sm">
                  These Freshsales owners have no CRM user with the same email or full name, so their records are imported without an owner. Invite
                  them under Users, then run the import again to assign them.
                </Text>
                <Text size="sm" mt={4}>
                  {Object.entries(report.unmatched_owners)
                    .map(([n, c]) => `${n} (${c})`)
                    .join(', ')}
                </Text>
              </Alert>
            )}
            {report.warnings.length > 0 && (
              <Alert color="gray" variant="light" title={`${report.warnings.length} warnings`}>
                <List size="xs">
                  {report.warnings.slice(0, 30).map((w, i) => (
                    <List.Item key={i}>{w}</List.Item>
                  ))}
                </List>
              </Alert>
            )}
          </Stack>
        )}
      </Stack>
    </Card>
  )
}
