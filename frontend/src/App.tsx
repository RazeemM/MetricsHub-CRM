import { Center, Loader } from '@mantine/core'
import type { ReactNode } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { useAuth } from './auth'
import Layout from './components/Layout'
import AccountDetail from './pages/AccountDetail'
import Accounts from './pages/Accounts'
import ContactDetail from './pages/ContactDetail'
import Contacts from './pages/Contacts'
import Campaigns, { CampaignDetail } from './pages/Campaigns'
import Dashboard from './pages/Dashboard'
import EmailTemplates, { EmailTemplateEdit } from './pages/EmailTemplates'
import ImportPage from './pages/Import'
import Insights from './pages/Insights'
import Login, { SsoCallback } from './pages/Login'
import MailingLists, { MailingListDetail } from './pages/MailingLists'
import OpportunityDetail from './pages/OpportunityDetail'
import OpportunityEdit from './pages/OpportunityEdit'
import Opportunities from './pages/Opportunities'
import PipelineBoard from './pages/PipelineBoard'
import Products from './pages/Products'
import QuoteTemplates from './pages/QuoteTemplates'
import Users from './pages/Users'
import WebForms, { WebFormDetail } from './pages/WebForms'

function Protected({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  const loc = useLocation()
  if (loading)
    return (
      <Center h="100vh">
        <Loader />
      </Center>
    )
  if (!user) return <Navigate to="/login" state={{ from: loc.pathname }} replace />
  return <>{children}</>
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/sso" element={<SsoCallback />} />
      <Route
        element={
          <Protected>
            <Layout />
          </Protected>
        }
      >
        <Route path="/" element={<Dashboard />} />
        <Route path="/pipeline" element={<PipelineBoard />} />
        <Route path="/insights" element={<Insights />} />
        <Route path="/opportunities" element={<Opportunities />} />
        <Route path="/opportunities/new" element={<OpportunityEdit />} />
        <Route path="/opportunities/:id" element={<OpportunityDetail />} />
        <Route path="/opportunities/:id/edit" element={<OpportunityEdit />} />
        <Route path="/accounts" element={<Accounts />} />
        <Route path="/accounts/:id" element={<AccountDetail />} />
        <Route path="/contacts" element={<Contacts />} />
        <Route path="/contacts/:id" element={<ContactDetail />} />
        <Route path="/products" element={<Products />} />
        <Route path="/quote-templates" element={<QuoteTemplates />} />
        <Route path="/email/campaigns" element={<Campaigns />} />
        <Route path="/email/campaigns/:id" element={<CampaignDetail />} />
        <Route path="/email/templates" element={<EmailTemplates />} />
        <Route path="/email/templates/:id" element={<EmailTemplateEdit />} />
        <Route path="/email/lists" element={<MailingLists />} />
        <Route path="/email/lists/:id" element={<MailingListDetail />} />
        <Route path="/import" element={<ImportPage />} />
        <Route path="/users" element={<Users />} />
        <Route path="/web-forms" element={<WebForms />} />
        <Route path="/web-forms/:id" element={<WebFormDetail />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
