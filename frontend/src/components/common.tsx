import { ActionIcon, Badge, Group, Pagination, Select, Stack, Text, Title, Tooltip, type SelectProps } from '@mantine/core'
import { IconHelp } from '@tabler/icons-react'
import { Link } from 'react-router-dom'
import { useDebouncedValue } from '@mantine/hooks'
import type { ReactNode } from 'react'
import { useMemo, useState } from 'react'
import { useAccountSearch, useContactSearch, useUsers } from '../hooks'
import type { Account, Contact } from '../types'
import { AccountFormModal, ContactFormModal } from './forms'
import { ACCOUNT_TYPE_COLORS, ACCOUNT_TYPES, LIFECYCLE_COLORS, LIFECYCLES } from '../labels'

/** Page title, subtitle and actions. `help` names a help topic, linked from a (?) next to the title. */
export function PageHeader({ title, subtitle, actions, help }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode; help?: string }) {
  return (
    <Group justify="space-between" mb="md" align="flex-start" wrap="wrap">
      <Stack gap={2}>
        <Group gap={6} wrap="nowrap">
          <Title order={2}>{title}</Title>
          {help && (
            <Tooltip label="Help for this page">
              <ActionIcon variant="subtle" color="gray" component={Link} to={`/help/${help}`} aria-label="Help for this page">
                <IconHelp size={18} />
              </ActionIcon>
            </Tooltip>
          )}
        </Group>
        {subtitle && (
          <Text c="dimmed" size="sm">
            {subtitle}
          </Text>
        )}
      </Stack>
      <Group gap="xs">{actions}</Group>
    </Group>
  )
}

export function Pager({ page, total, pageSize, onChange }: { page: number; total: number; pageSize: number; onChange: (p: number) => void }) {
  const pages = Math.ceil(total / pageSize)
  return (
    <Group justify="space-between" mt="sm">
      <Text size="sm" c="dimmed">
        {total} record{total === 1 ? '' : 's'}
      </Text>
      {pages > 1 && <Pagination value={page} onChange={onChange} total={pages} size="sm" />}
    </Group>
  )
}

export const LifecycleBadge = ({ value }: { value: string }) => (
  <Badge variant="light" color={LIFECYCLE_COLORS[value] ?? 'gray'}>
    {LIFECYCLES[value] ?? value}
  </Badge>
)
export const AccountTypeBadge = ({ value }: { value: string }) => (
  <Badge variant="light" color={ACCOUNT_TYPE_COLORS[value] ?? 'gray'}>
    {ACCOUNT_TYPES[value] ?? value}
  </Badge>
)

type PickerProps = Omit<SelectProps, 'data' | 'value' | 'onChange'> & {
  value: number | null | undefined
  onChange: (id: number | null) => void
  initialLabel?: string | null
}

const NEW = '__new'

/** Adds "+ Add “typed text” as a new …" when nothing listed matches what was typed. */
function withCreate(options: { value: string; label: string }[], search: string, value: number | null | undefined, what: string, allow?: boolean) {
  const q = search.trim()
  const selected = options.find((o) => o.value === String(value ?? ''))
  if (!allow || !q || q === selected?.label || options.some((o) => o.label.toLowerCase() === q.toLowerCase())) return options
  return [...options, { value: NEW, label: `+ Add "${q}" as a new ${what}` }]
}

/** Searchable account picker (server-side search). With allowCreate, offers to add the typed name as a new account. */
export function AccountPicker({
  value,
  onChange,
  initialLabel,
  types,
  allowCreate,
  ...rest
}: PickerProps & { types?: string[]; allowCreate?: boolean }) {
  const [search, setSearch] = useState('')
  const [debounced] = useDebouncedValue(search, 250)
  const { data } = useAccountSearch(debounced, types)
  const [creating, setCreating] = useState<string | null>(null)
  const [created, setCreated] = useState<{ value: string; label: string } | null>(null)
  const options = (data?.items ?? []).map((a) => ({ value: String(a.id), label: a.name }))
  const label = created?.value === String(value) ? created.label : initialLabel
  if (value && label && !options.some((o) => o.value === String(value))) options.unshift({ value: String(value), label })
  const accountType = types?.[0]
  const defaults = useMemo(
    () => ({ name: creating ?? '', ...(accountType ? { account_type: accountType as Account['account_type'] } : {}) }),
    [creating, accountType],
  )
  const what = types?.length === 1 ? (ACCOUNT_TYPES[types[0]] ?? 'account').toLowerCase() : 'account'
  return (
    <>
      <Select
        searchable
        clearable
        data={withCreate(options, debounced, value, what, allowCreate)}
        value={value ? String(value) : null}
        onChange={(v) => (v === NEW ? setCreating(search.trim()) : onChange(v ? Number(v) : null))}
        onSearchChange={setSearch}
        nothingFoundMessage="No matching account"
        filter={({ options }) => options}
        {...rest}
      />
      {allowCreate && (
        <AccountFormModal
          opened={creating !== null}
          onClose={() => setCreating(null)}
          defaults={defaults}
          onSaved={(a) => {
            setCreated({ value: String(a.id), label: a.name })
            onChange(a.id)
          }}
        />
      )}
    </>
  )
}

export function ContactPicker({
  value,
  onChange,
  initialLabel,
  accountId,
  roles,
  allowCreate,
  ...rest
}: PickerProps & { accountId?: number | null; roles?: string[]; allowCreate?: boolean }) {
  const [search, setSearch] = useState('')
  const [debounced] = useDebouncedValue(search, 250)
  const { data } = useContactSearch(debounced, accountId, roles)
  const [creating, setCreating] = useState<string | null>(null)
  const [created, setCreated] = useState<{ value: string; label: string } | null>(null)
  const options = (data?.items ?? []).map((c) => ({
    value: String(c.id),
    label: `${c.full_name}${c.account ? ` (${c.account.name})` : ''}`,
  }))
  const label = created?.value === String(value) ? created.label : initialLabel
  if (value && label && !options.some((o) => o.value === String(value))) options.unshift({ value: String(value), label })
  const role = roles?.[0]
  const defaults = useMemo(() => {
    const [first, ...last] = (creating ?? '').split(/\s+/)
    return {
      ...(creating?.includes('@') ? { email: creating } : { first_name: first, last_name: last.join(' ') }),
      account_id: accountId ?? null,
      ...(role ? { role: role as Contact['role'] } : {}),
    }
  }, [creating, accountId, role])
  return (
    <>
      <Select
        searchable
        clearable
        data={withCreate(options, debounced, value, 'contact', allowCreate)}
        value={value ? String(value) : null}
        onChange={(v) => (v === NEW ? setCreating(search.trim()) : onChange(v ? Number(v) : null))}
        onSearchChange={setSearch}
        nothingFoundMessage="No matching contact"
        filter={({ options }) => options}
        {...rest}
      />
      {allowCreate && (
        <ContactFormModal
          opened={creating !== null}
          onClose={() => setCreating(null)}
          defaults={defaults}
          onSaved={(c) => {
            setCreated({ value: String(c.id), label: c.full_name })
            onChange(c.id)
          }}
        />
      )}
    </>
  )
}

export function UserPicker({ value, onChange, ...rest }: PickerProps) {
  const { data } = useUsers()
  return (
    <Select
      searchable
      clearable
      data={(data ?? []).filter((u) => u.is_active).map((u) => ({ value: String(u.id), label: u.full_name }))}
      value={value ? String(value) : null}
      onChange={(v) => onChange(v ? Number(v) : null)}
      {...rest}
    />
  )
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Stack gap={0}>
      <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
        {label}
      </Text>
      <Text size="sm" component="div">
        {children || '—'}
      </Text>
    </Stack>
  )
}
