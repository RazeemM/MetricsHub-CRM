import { Alert, Button, Center, Divider, Paper, PasswordInput, Stack, Text, TextInput, Title } from '@mantine/core'
import { IconBrandWindows, IconLock } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Navigate, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../auth'
import { Logo } from '../components/Logo'

interface AuthConfig {
  sso_enabled: boolean
  sso_label: string
  password_login_enabled: boolean
}

export default function Login() {
  const { user, login } = useAuth()
  const nav = useNavigate()
  const loc = useLocation()
  const [params] = useSearchParams()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(params.get('sso_error'))
  const [busy, setBusy] = useState(false)
  const { data: cfg } = useQuery({
    queryKey: ['auth-config'],
    queryFn: async () => (await fetch('/api/auth/config')).json() as Promise<AuthConfig>,
  })

  if (user) return <Navigate to={(loc.state as { from?: string } | null)?.from ?? '/'} replace />

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(email, password)
      nav('/')
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Center mih="100vh" bg="navy.9" p="md">
      <Paper w={400} maw="100%" p="xl" radius="lg" shadow="xl">
        <Stack gap="lg">
          <Stack gap={4} align="center">
            <Logo size={36} />
            <Title order={3}>MetricsHub &amp; Sentry CRM</Title>
            <Text size="sm" c="dimmed">
              Sign in to continue
            </Text>
          </Stack>
          {error && (
            <Alert color="red" variant="light">
              {error}
            </Alert>
          )}
          {cfg?.sso_enabled && (
            <Button
              component="a"
              href="/api/auth/sso/login"
              size="md"
              variant="default"
              leftSection={<IconBrandWindows size={18} />}
            >
              {cfg.sso_label}
            </Button>
          )}
          {cfg?.sso_enabled && cfg.password_login_enabled && <Divider label="or with a password" />}
          {(cfg?.password_login_enabled ?? true) && (
            <form onSubmit={submit}>
              <Stack>
                <TextInput label="Email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoFocus />
                <PasswordInput label="Password" required value={password} onChange={(e) => setPassword(e.target.value)} />
                <Button type="submit" loading={busy} leftSection={<IconLock size={16} />}>
                  Sign in
                </Button>
              </Stack>
            </form>
          )}
        </Stack>
      </Paper>
    </Center>
  )
}

/** Landing page after SSO: the token arrives in the URL fragment (never sent to servers or logs). */
export function SsoCallback() {
  const { loginWithToken } = useAuth()
  const nav = useNavigate()
  useEffect(() => {
    const token = new URLSearchParams(window.location.hash.slice(1)).get('token')
    window.history.replaceState(null, '', '/sso')
    if (!token) {
      nav('/login?sso_error=Missing+token', { replace: true })
      return
    }
    loginWithToken(token).then(
      () => nav('/', { replace: true }),
      () => nav('/login?sso_error=Sign-in+failed', { replace: true }),
    )
  }, [loginWithToken, nav])
  return (
    <Center h="100vh">
      <Text>Signing you in…</Text>
    </Center>
  )
}
