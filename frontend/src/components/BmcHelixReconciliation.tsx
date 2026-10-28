import { Alert, Anchor, Badge, Button, Card, Checkbox, Group, List, ScrollArea, SegmentedControl, Stack, Table, Text, Title } from '@mantine/core'
import { Dropzone } from '@mantine/dropzone'
import { modals } from '@mantine/modals'
import { notifications } from '@mantine/notifications'
import { IconCloudUpload } from '@tabler/icons-react'
import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'

interface Change {
  action: string
  sheet: string
  name: string
  email: string
  new_email: string | null
  account: string | null
  contact_id: number | null
  detail: string
}

interface Report {
  dry_run: boolean
  file: string
  rows: number
  rows_by_sheet: Record<string, number>
  counts: Record<string, number>
  changes: Change[]
  warnings: string[]
}

const SHEETS: Record<string, string> = {
  match: 'Probable matches',
  not_found: 'Not found',
  ambiguous: 'Ambiguous',
  already_helix: 'Already Helix',
}

const ACTIONS: Record<string, { label: string; color: string }> = {
  email_updated: { label: 'Moved to Helix address', color: 'violet' },
  merged: { label: 'Merged duplicates', color: 'grape' },
  created: { label: 'Created', color: 'green' },
  updated: { label: 'Completed', color: 'blue' },
  unchanged: { label: 'Already up to date', color: 'gray' },
  skipped_ambiguous: { label: 'Skipped: ambiguous', color: 'orange' },
  skipped_match: { label: 'Skipped: match not applied', color: 'orange' },
  skipped_missing: { label: 'Skipped: not in the CRM', color: 'orange' },
}

/** Moves BMC contacts to their BMC Helix address from the reconciliation workbook (rapprochement_bmc_helix_historique.xlsx). */
export function BmcHelixReconciliation() {
  const qc = useQueryClient()
  const [file, setFile] = useState<File | null>(null)
  const [applyMatches, setApplyMatches] = useState(true)
  const [createMissing, setCreateMissing] = useState(true)
  const [report, setReport] = useState<Report | null>(null)
  const [busy, setBusy] = useState(false)
  const [show, setShow] = useState('all')

  const run = async (commit: boolean) => {
    if (!file) return
    setBusy(true)
    try {
      const form = new FormData()
      form.append('file', file)
      form.append('commit', String(commit))
      form.append('apply_matches', String(applyMatches))
      form.append('create_missing', String(createMissing))
      const r = await api<Report>('/migrations/bmc-helix', { method: 'POST', form })
      setReport(r)
      if (commit) {
        notifications.show({ color: 'green', message: 'BMC Helix addresses applied' })
        ;['contacts', 'accounts', 'imports', 'audiences', 'lists'].forEach((k) => qc.invalidateQueries({ queryKey: [k] }))
      }
    } catch (e) {
      notifications.show({ color: 'red', message: (e as Error).message })
    } finally {
      setBusy(false)
    }
  }
  const changes = report?.changes.filter((c) => show === 'all' || c.action === show) ?? []

  return (
    <Card withBorder mb="md">
      <Title order={5}>BMC → BMC Helix contact addresses</Title>
      <Text size="sm" c="dimmed" mb="sm">
        Upload the reconciliation workbook (<i>rapprochement_bmc_helix_historique.xlsx</i>). Contacts in <b>Correspondances</b> move from their @bmc.com address to the
        observed Helix address. If both addresses already exist, the two contacts are merged, with timeline, deals, lists and campaign history kept. Contacts in{' '}
        <b>Non trouvés</b> and <b>Déjà Helix</b> are created if they are missing. <b>Ambigus</b> rows are never applied. The old address is kept on each contact as a previous
        address, and the change is noted on its timeline.
      </Text>
      <Stack>
        <Dropzone
          multiple={false}
          onDrop={(f) => {
            setFile(f[0] ?? null)
            setReport(null)
          }}
          maxSize={20 * 1024 * 1024}
          accept={{ 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'] }}
        >
          <Group justify="center" gap="sm" mih={60} style={{ pointerEvents: 'none' }}>
            <IconCloudUpload size={26} stroke={1.5} />
            <Text size="sm">{file ? file.name : 'Drop the reconciliation workbook (.xlsx)'}</Text>
          </Group>
        </Dropzone>
        <Group>
          <Checkbox
            label="Move contacts to the probable Helix address"
            description="The workbook marks these as probable (full name only): uncheck to review them first"
            checked={applyMatches}
            onChange={(e) => (setApplyMatches(e.currentTarget.checked), setReport(null))}
          />
          <Checkbox label="Create contacts that are not in the CRM" checked={createMissing} onChange={(e) => (setCreateMissing(e.currentTarget.checked), setReport(null))} />
        </Group>
        <Group>
          <Button variant="default" disabled={!file} loading={busy} onClick={() => run(false)}>
            Dry run
          </Button>
          <Button
            disabled={!report || !report.dry_run}
            loading={busy}
            onClick={() =>
              modals.openConfirmModal({
                title: 'Apply to the CRM?',
                children: (
                  <Text size="sm">
                    This makes the changes shown in the dry run. Merged contacts cannot be split again. Running the same workbook again later changes nothing more.
                  </Text>
                ),
                labels: { confirm: 'Apply', cancel: 'Cancel' },
                onConfirm: () => run(true),
              })
            }
          >
            Apply
          </Button>
        </Group>

        {report && (
          <Stack gap="sm">
            <Alert color={report.dry_run ? 'blue' : 'green'} variant="light" title={report.dry_run ? 'Dry run: nothing written yet' : 'Applied'}>
              <Text size="sm">
                {report.rows} rows ·{' '}
                {Object.entries(report.rows_by_sheet)
                  .map(([k, v]) => `${SHEETS[k] ?? k} ${v}`)
                  .join(' · ')}
              </Text>
              <Group gap={6} mt={6}>
                {Object.entries(report.counts).map(([k, v]) => (
                  <Badge key={k} color={ACTIONS[k]?.color ?? 'gray'} variant="light" tt="none">
                    {ACTIONS[k]?.label ?? k}: {v}
                  </Badge>
                ))}
              </Group>
            </Alert>
            {report.warnings.length > 0 && (
              <Alert color="orange" variant="light" title={`${report.warnings.length} warnings`}>
                <List size="xs">
                  {report.warnings.slice(0, 30).map((w, i) => (
                    <List.Item key={i}>{w}</List.Item>
                  ))}
                </List>
              </Alert>
            )}
            {report.changes.length > 0 && (
              <>
                <SegmentedControl
                  size="xs"
                  value={show}
                  onChange={setShow}
                  data={[
                    { value: 'all', label: `All (${report.changes.length})` },
                    ...Object.keys(report.counts)
                      .filter((k) => k !== 'unchanged')
                      .map((k) => ({ value: k, label: `${ACTIONS[k]?.label ?? k} (${report.counts[k]})` })),
                  ]}
                />
                <ScrollArea.Autosize mah={480} type="auto" offsetScrollbars>
                  <Table fz="sm" miw={860} stickyHeader striped>
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>Action</Table.Th>
                        <Table.Th>Name</Table.Th>
                        <Table.Th>Address in the workbook</Table.Th>
                        <Table.Th>Helix address</Table.Th>
                        <Table.Th>Account</Table.Th>
                        <Table.Th>Detail</Table.Th>
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {changes.map((c, i) => (
                        <Table.Tr key={i}>
                          <Table.Td>
                            <Badge size="sm" color={ACTIONS[c.action]?.color ?? 'gray'} variant="light" tt="none">
                              {ACTIONS[c.action]?.label ?? c.action}
                            </Badge>
                          </Table.Td>
                          <Table.Td>
                            {c.contact_id && !report.dry_run ? (
                              <Anchor component={Link} to={`/contacts/${c.contact_id}`} size="sm">
                                {c.name}
                              </Anchor>
                            ) : (
                              c.name
                            )}
                          </Table.Td>
                          <Table.Td>{c.email}</Table.Td>
                          <Table.Td>{c.new_email}</Table.Td>
                          <Table.Td>{c.account}</Table.Td>
                          <Table.Td>
                            <Text size="xs" c="dimmed">
                              {c.detail}
                            </Text>
                          </Table.Td>
                        </Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                </ScrollArea.Autosize>
              </>
            )}
          </Stack>
        )}
      </Stack>
    </Card>
  )
}
