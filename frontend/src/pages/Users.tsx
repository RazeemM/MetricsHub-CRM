import { Badge, Button, Card, Group, Modal, PasswordInput, Select, Stack, Switch, Table, Text, TextInput } from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { IconPlus } from '@tabler/icons-react'
import { useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { PageHeader } from '../components/common'
import { useApiMutation, useBrands, useUsers } from '../hooks'
import { fmtDate } from '../labels'
import type { User } from '../types'

const ROLES = [
  { value: 'admin', label: 'Admin' },
  { value: 'sales', label: 'Sales' },
  { value: 'readonly', label: 'Read-only' },
]

function UserModal({ opened, onClose, user }: { opened: boolean; onClose: () => void; user: User | null }) {
  const { data: brands } = useBrands()
  const [v, setV] = useState({ email: '', full_name: '', role: 'sales', brand_id: null as number | null, is_active: true, password: '' })
  useEffect(() => {
    if (opened)
      setV(user ? { email: user.email, full_name: user.full_name, role: user.role, brand_id: user.brand_id, is_active: user.is_active, password: '' } : { email: '', full_name: '', role: 'sales', brand_id: null, is_active: true, password: '' })
  }, [opened, user])
  const save = useApiMutation(
    () => {
      const body: Record<string, unknown> = { ...v }
      if (!v.password) delete body.password
      if (user) delete body.email
      return user ? api(`/users/${user.id}`, { method: 'PATCH', body }) : api('/users', { method: 'POST', body })
    },
    { invalidate: [['users']], success: 'User saved', onSuccess: onClose },
  )
  return (
    <Modal opened={opened} onClose={onClose} title={user ? 'Edit user' : 'Invite user'}>
      <Stack>
        <TextInput label="Email" required disabled={!!user} value={v.email} onChange={(e) => setV({ ...v, email: e.target.value })} />
        <TextInput label="Full name" required value={v.full_name} onChange={(e) => setV({ ...v, full_name: e.target.value })} />
        <Select label="Role" data={ROLES} value={v.role} onChange={(x) => setV({ ...v, role: x ?? 'sales' })} allowDeselect={false} />
        <Select
          label="Main brand"
          description="Default brand for new opportunities"
          data={(brands ?? []).map((b) => ({ value: String(b.id), label: b.name }))}
          value={v.brand_id ? String(v.brand_id) : null}
          onChange={(x) => setV({ ...v, brand_id: x ? Number(x) : null })}
          clearable
        />
        <PasswordInput
          label={user ? 'New password (optional)' : 'Password'}
          description="Leave empty for SSO-only users"
          value={v.password}
          onChange={(e) => setV({ ...v, password: e.target.value })}
        />
        {user && <Switch label="Active" checked={v.is_active} onChange={(e) => setV({ ...v, is_active: e.currentTarget.checked })} />}
        <Group justify="flex-end">
          <Button loading={save.isPending} onClick={() => save.mutate(undefined)} disabled={!v.email || !v.full_name}>
            Save
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}

export default function Users() {
  const { isAdmin } = useAuth()
  const { data: users } = useUsers()
  const { data: brands } = useBrands()
  const [opened, modal] = useDisclosure()
  const [editing, setEditing] = useState<User | null>(null)
  if (!isAdmin) return <Navigate to="/" />
  return (
    <>
      <PageHeader
        title="Users"
        subtitle="People who can sign in to the CRM. With SSO, users from allowed domains are created on first sign-in."
        actions={
          <Button
            leftSection={<IconPlus size={16} />}
            onClick={() => {
              setEditing(null)
              modal.open()
            }}
          >
            Invite user
          </Button>
        }
      />
      <Card withBorder p={0}>
        <Table highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Name</Table.Th>
              <Table.Th>Email</Table.Th>
              <Table.Th>Role</Table.Th>
              <Table.Th>Brand</Table.Th>
              <Table.Th>Last sign-in</Table.Th>
              <Table.Th>Status</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {users?.map((u) => (
              <Table.Tr
                key={u.id}
                className="clickable-row"
                onClick={() => {
                  setEditing(u)
                  modal.open()
                }}
              >
                <Table.Td fw={500}>{u.full_name}</Table.Td>
                <Table.Td>{u.email}</Table.Td>
                <Table.Td>{ROLES.find((r) => r.value === u.role)?.label}</Table.Td>
                <Table.Td>{brands?.find((b) => b.id === u.brand_id)?.name}</Table.Td>
                <Table.Td>
                  <Text size="sm">{fmtDate((u as User & { last_login_at?: string }).last_login_at)}</Text>
                </Table.Td>
                <Table.Td>
                  <Badge color={u.is_active ? 'green' : 'gray'} variant="light">
                    {u.is_active ? 'Active' : 'Disabled'}
                  </Badge>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Card>
      <UserModal opened={opened} onClose={modal.close} user={editing} />
    </>
  )
}
