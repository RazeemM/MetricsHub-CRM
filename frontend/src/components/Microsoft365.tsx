import { Alert, Anchor, Badge, Button, Checkbox, Code, Group, Stack, Table, Text, TextInput } from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { IconBrandOffice, IconPlugConnected } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useApiMutation } from '../hooks'
import { fmtDate } from '../labels'

/** The signed-in user's Microsoft 365 sign-in for sending email (CRM_MAIL_BACKEND=graph_delegated). */
export interface MailConnection {
  required: boolean
  enabled: boolean
  sender: string | null
  connected: boolean
  account: string | null
  connected_at: string | null
  last_used_at: string | null
  last_error: string | null
  used_for_automatic: boolean
  redirect_uri: string | null
}

export const useMailConnection = (enabled = true) =>
  useQuery({ queryKey: ['mail-connection'], queryFn: () => api<MailConnection>('/mail/microsoft/connection'), enabled })

/** Opens the Microsoft sign-in; it comes back to the current page. */
export function ConnectMicrosoft365({ label = 'Connect Microsoft 365', size = 'sm' }: { label?: string; size?: string }) {
  const loc = useLocation()
  const connect = useApiMutation(() => api<{ url: string }>('/mail/microsoft/connect', { method: 'POST', body: { return_to: loc.pathname + loc.search } }), {
    onSuccess: (r) => {
      window.location.href = r.url
    },
  })
  return (
    <Button size={size} leftSection={<IconBrandOffice size={16} />} loading={connect.isPending} onClick={() => connect.mutate(undefined)}>
      {label}
    </Button>
  )
}

/** In an email dialog: sending needs the user's own Microsoft 365 sign-in first. */
export function ConnectMicrosoft365Alert({ sender }: { sender: string | null }) {
  return (
    <Alert color="blue" variant="light" icon={<IconPlugConnected size={18} />} title="Connect Microsoft 365 to send">
      <Text size="sm" mb="xs">
        Email is sent as <b>{sender}</b> with your Microsoft 365 account, which needs Send As rights on that mailbox. Sign in once (with MFA); the CRM then sends for you until the sign-in expires.
      </Text>
      <ConnectMicrosoft365 size="xs" />
    </Alert>
  )
}

/** Shows the result of a Microsoft sign-in (?microsoft365=connected or ?microsoft365_error=...) and removes it from the URL. */
export function useMicrosoft365Return() {
  const loc = useLocation()
  const nav = useNavigate()
  useEffect(() => {
    const q = new URLSearchParams(loc.search)
    const ok = q.get('microsoft365')
    const err = q.get('microsoft365_error')
    if (!ok && !err) return
    if (ok) notifications.show({ color: 'green', message: 'Microsoft 365 connected: you can send email' })
    else notifications.show({ color: 'red', title: 'Microsoft 365 not connected', message: err, autoClose: false })
    q.delete('microsoft365')
    q.delete('microsoft365_error')
    nav({ pathname: loc.pathname, search: q.toString() }, { replace: true })
  }, [loc.pathname, loc.search, nav])
}

interface SenderSettings {
  from: string | null
  from_name: string | null
  default_from: string | null
  default_from_name: string | null
  backend: string
  delegated: boolean
  service_user: { id: number; name: string; account: string; last_error: string | null } | null
  connections: { user: string; email: string; account: string; connected_at: string; last_used_at: string | null; last_error: string | null }[]
}

/** Admin card on System status: who email is sent as, and the Microsoft 365 sign-ins that send it. */
export function SenderSettingsCard() {
  const { data: s } = useQuery({ queryKey: ['mail-sender'], queryFn: () => api<SenderSettings>('/mail/sender') })
  const { data: me } = useMailConnection()
  const [from, setFrom] = useState('')
  const [name, setName] = useState('')
  useEffect(() => {
    if (!s) return
    setFrom(s.from ?? '')
    setName(s.from_name ?? '')
  }, [s])
  const save = useApiMutation(
    (body: { from_address: string | null; from_name: string | null; use_my_connection_for_automatic?: boolean }) => api('/mail/sender', { method: 'PUT', body }),
    { invalidate: [['mail-sender'], ['mail-connection'], ['mail-settings']], success: 'Email sender saved' },
  )
  const disconnect = useApiMutation(() => api('/mail/microsoft/connection', { method: 'DELETE' }), {
    invalidate: [['mail-sender'], ['mail-connection']],
    success: 'Microsoft 365 disconnected',
  })
  if (!s) return null
  const current = { from_address: from.trim() || null, from_name: name.trim() || null }
  const dirty = (from.trim() || null) !== s.from || (name.trim() || null) !== s.from_name

  return (
    <Stack gap="sm" mb="md">
      <Group align="flex-end" gap="xs">
        <TextInput size="xs" label="Send email as" placeholder={s.default_from ?? 'crm@sentrysoftware.com'} value={from} onChange={(e) => setFrom(e.target.value)} w={280} description="Every quote, email and notice, whoever sends it" />
        <TextInput size="xs" label="Sender name" placeholder={s.default_from_name ?? 'Sentry Software'} value={name} onChange={(e) => setName(e.target.value)} w={220} description="Emails written in the CRM show the user's name" />
        <Button size="xs" disabled={!dirty} loading={save.isPending} onClick={() => save.mutate(current)}>
          Save
        </Button>
      </Group>
      {s.default_from && (
        <Text size="xs" c="dimmed">
          Empty: the server default, {s.default_from} (CRM_MAIL_FROM).
        </Text>
      )}
      {s.delegated ? (
        <>
          <Text size="sm">
            Microsoft 365, delegated: each user sends with their own Microsoft 365 sign-in and needs <b>Send As</b> on {s.from ?? s.default_from} in Exchange.
          </Text>
          <Group gap="xs">
            {me?.connected ? (
              <>
                <Badge color={me.last_error ? 'red' : 'green'} variant="light" tt="none">
                  You: {me.account}
                </Badge>
                <ConnectMicrosoft365 size="xs" label="Reconnect" />
                <Button size="xs" variant="subtle" color="red" loading={disconnect.isPending} onClick={() => disconnect.mutate(undefined)}>
                  Disconnect
                </Button>
              </>
            ) : (
              <ConnectMicrosoft365 size="xs" />
            )}
          </Group>
          {me?.last_error && (
            <Text size="xs" c="red">
              {me.last_error}
            </Text>
          )}
          <Checkbox
            size="xs"
            disabled={!me?.connected}
            checked={!!me?.used_for_automatic}
            onChange={(e) => save.mutate({ ...current, use_my_connection_for_automatic: e.currentTarget.checked })}
            label={
              s.service_user
                ? `Automatic emails (campaigns, renewal notices, form confirmations) are sent with ${s.service_user.name}'s sign-in (${s.service_user.account})`
                : 'Send automatic emails (campaigns, renewal notices, form confirmations) with my sign-in. None is chosen yet, so they cannot be sent.'
            }
          />
          {me?.redirect_uri && (
            <Text size="xs" c="dimmed">
              Redirect URI to register (Web platform) in the Entra ID app registration: <Code>{me.redirect_uri}</Code>. Delegated permissions: Mail.Send.Shared, offline_access, openid, profile.
            </Text>
          )}
          {s.connections.length > 0 && (
            <Table fz="xs" verticalSpacing={2} withTableBorder>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>User</Table.Th>
                  <Table.Th>Microsoft 365 account</Table.Th>
                  <Table.Th>Connected</Table.Th>
                  <Table.Th>Last used</Table.Th>
                  <Table.Th>Problem</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {s.connections.map((c) => (
                  <Table.Tr key={c.email}>
                    <Table.Td>{c.user}</Table.Td>
                    <Table.Td>{c.account}</Table.Td>
                    <Table.Td>{fmtDate(c.connected_at)}</Table.Td>
                    <Table.Td>{c.last_used_at ? fmtDate(c.last_used_at) : '—'}</Table.Td>
                    <Table.Td c={c.last_error ? 'red' : undefined}>{c.last_error ?? '—'}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}
        </>
      ) : (
        <Text size="xs" c="dimmed">
          To send with each user's Microsoft 365 sign-in and Send As on a shared mailbox, set CRM_MAIL_BACKEND=graph_delegated.{' '}
          <Anchor href="/help/email-setup" size="xs">
            Help
          </Anchor>
        </Text>
      )}
    </Stack>
  )
}
