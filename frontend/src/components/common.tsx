import { Badge, Group, Pagination, Select, Stack, Text, Title, type SelectProps } from '@mantine/core'
import { useDebouncedValue } from '@mantine/hooks'
import type { ReactNode } from 'react'
import { useState } from 'react'
import { useAccountSearch, useContactSearch, useUsers } from '../hooks'
import { ACCOUNT_TYPE_COLORS, ACCOUNT_TYPES, LIFECYCLE_COLORS, LIFECYCLES } from '../labels'

export function PageHeader({ title, subtitle, actions }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <Group justify="space-between" mb="md" align="flex-start" wrap="wrap">
      <Stack gap={2}>
        <Title order={2}>{title}</Title>
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

/** Searchable account picker (server-side search). */
export function AccountPicker({ value, onChange, initialLabel, types, ...rest }: PickerProps & { types?: string[] }) {
  const [search, setSearch] = useState('')
  const [debounced] = useDebouncedValue(search, 250)
  const { data } = useAccountSearch(debounced, types)
  const options = (data?.items ?? []).map((a) => ({ value: String(a.id), label: a.name }))
  if (value && initialLabel && !options.some((o) => o.value === String(value)))
    options.unshift({ value: String(value), label: initialLabel })
  return (
    <Select
      searchable
      clearable
      data={options}
      value={value ? String(value) : null}
      onChange={(v) => onChange(v ? Number(v) : null)}
      onSearchChange={setSearch}
      nothingFoundMessage="No matching account"
      filter={({ options }) => options}
      {...rest}
    />
  )
}

export function ContactPicker({
  value,
  onChange,
  initialLabel,
  accountId,
  roles,
  ...rest
}: PickerProps & { accountId?: number | null; roles?: string[] }) {
  const [search, setSearch] = useState('')
  const [debounced] = useDebouncedValue(search, 250)
  const { data } = useContactSearch(debounced, accountId, roles)
  const options = (data?.items ?? []).map((c) => ({
    value: String(c.id),
    label: `${c.full_name}${c.account ? ` (${c.account.name})` : ''}`,
  }))
  if (value && initialLabel && !options.some((o) => o.value === String(value)))
    options.unshift({ value: String(value), label: initialLabel })
  return (
    <Select
      searchable
      clearable
      data={options}
      value={value ? String(value) : null}
      onChange={(v) => onChange(v ? Number(v) : null)}
      onSearchChange={setSearch}
      nothingFoundMessage="No matching contact"
      filter={({ options }) => options}
      {...rest}
    />
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
