import React, { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import api from '../api'
import { Card, Badge } from '../components/ui'

const PROJECT_TYPES = [
  { value: 'dapp', label: 'dApp' },
  { value: 'ecosystem', label: 'Ecosystem' },
]

const TASK_TYPES = [
  { value: '', label: '— No task yet, I\'ll add one later —' },
  { value: 'swap', label: 'Swap' },
  { value: 'bridge', label: 'Bridge' },
  { value: 'stake', label: 'Stake' },
  { value: 'transfer', label: 'Transfer' },
  { value: 'provide_liquidity', label: 'Provide liquidity' },
  { value: 'interact_contract', label: 'Generic contract interaction' },
]

// Contract param key each task type's build_transaction_params() expects —
// mirrors backend/telegram/project_wizard.py's _CONTRACT_PARAM_BY_TASK_TYPE
// so the two guided flows (Telegram + website) stay consistent.
const CONTRACT_PARAM_BY_TASK_TYPE = {
  swap: 'router_address',
  bridge: 'bridge_contract',
  stake: 'staking_contract',
  provide_liquidity: 'router_address',
  interact_contract: 'contract_address',
}

const STEP_LABELS = ['Details', 'Chains', 'Socials', 'Task', 'Review', 'Criteria']

function isValidAddress(addr) {
  return /^0x[a-fA-F0-9]{40}$/.test(addr || '')
}

export default function AddProject() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const existingId = searchParams.get('project')  // ?project=ID jumps straight to the criteria step
  const [step, setStep] = useState(existingId ? 5 : 0)
  const [chains, setChains] = useState([])
  const [chainsLoaded, setChainsLoaded] = useState(false)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [createdProjectId, setCreatedProjectId] = useState(existingId ? Number(existingId) : null)

  const [form, setForm] = useState({
    name: '',
    type: 'dapp',
    chain_ids: [],
    website: '',
    twitter: '',
    discord: '',
    task_enabled: false,
    task_type: '',
    task_chain_id: '',
    task_min_amount: '',
    task_max_amount: '',
    task_contract_address: '',
    criteria_docs_url: '',
  })

  const [draft, setDraft] = useState(null)
  const [draftLoading, setDraftLoading] = useState(false)
  const [draftError, setDraftError] = useState('')

  React.useEffect(() => {
    api.get('/chains/').then(r => { setChains(r.data); setChainsLoaded(true) }).catch(() => setChainsLoaded(true))
  }, [])

  const set = (patch) => setForm(f => ({ ...f, ...patch }))

  const toggleChain = (id) => {
    set({ chain_ids: form.chain_ids.includes(id) ? form.chain_ids.filter(c => c !== id) : [...form.chain_ids, id] })
  }

  const validateStep = () => {
    setError('')
    if (step === 0) {
      if (!form.name.trim()) { setError('Project name is required.'); return false }
    }
    if (step === 3 && form.task_enabled) {
      if (!form.task_type) { setError('Choose a task type, or turn off "add a task now".'); return false }
      if (!form.task_chain_id) { setError('Choose which chain this task runs on.'); return false }
      const min = parseFloat(form.task_min_amount), max = parseFloat(form.task_max_amount)
      if (!(min > 0) || !(max >= min)) { setError('Enter a valid min/max amount (max ≥ min, both > 0).'); return false }
      if (form.task_contract_address && !isValidAddress(form.task_contract_address)) {
        setError('Contract address must be a valid 0x address (42 chars).'); return false
      }
    }
    return true
  }

  const next = () => { if (validateStep()) setStep(s => Math.min(s + 1, 4)) }
  const back = () => { setError(''); setStep(s => Math.max(s - 1, 0)) }

  const fetchDraft = async () => {
    if (!form.criteria_docs_url.trim()) return
    setDraftLoading(true)
    setDraftError('')
    setDraft(null)
    try {
      const r = await api.post(`/projects/${createdProjectId}/criteria/draft`, { docs_url: form.criteria_docs_url })
      setDraft(r.data)
    } catch (e) {
      setDraftError(e?.response?.data?.detail || 'Could not draft criteria from that URL.')
    } finally {
      setDraftLoading(false)
    }
  }

  const acceptDraft = async () => {
    if (!draft?.draft_criteria?.length) return
    setSubmitting(true)
    try {
      await api.post(`/projects/${createdProjectId}/criteria/accept`, { criteria: draft.draft_criteria })
      navigate(`/projects`)
    } catch (e) {
      setDraftError('Could not save criteria.')
    } finally {
      setSubmitting(false)
    }
  }

  const createProject = async () => {
    setSubmitting(true)
    setError('')
    try {
      const payload = {
        name: form.name,
        type: form.type,
        chain_ids: form.chain_ids,
        website: form.website || null,
        twitter: form.twitter || null,
        discord: form.discord || null,
      }
      // If a previous attempt already created the project (e.g. only the task call failed),
      // reuse it instead of creating a duplicate.
      let projectId = createdProjectId
      if (!projectId) {
        const projRes = await api.post('/projects/', payload)
        projectId = projRes.data.id
        setCreatedProjectId(projectId)
      }

      if (form.task_enabled && form.task_type) {
        const paramKey = CONTRACT_PARAM_BY_TASK_TYPE[form.task_type]
        const parameters = {}
        if (paramKey && form.task_contract_address) parameters[paramKey] = form.task_contract_address
        await api.post(`/projects/${projectId}/tasks`, {
          project_id: projectId,
          task_type: form.task_type,
          chain_id: Number(form.task_chain_id),
          parameters,
          min_amount: parseFloat(form.task_min_amount),
          max_amount: parseFloat(form.task_max_amount),
          enabled: !!form.task_contract_address,
        })
      }

      setStep(5) // optional AI-drafted criteria step (skippable)
    } catch (e) {
      setError(e?.response?.data?.detail || 'Error creating project. Check the fields and try again.')
    } finally {
      setSubmitting(false)
    }
  }

  const isReview = step === 4
  const isCriteriaStep = step === 5 && createdProjectId

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20, maxWidth: 640 }}>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {STEP_LABELS.map((label, i) => (
          <span
            key={label}
            className={`badge ${i === step ? 'success' : i < step ? 'neutral' : 'neutral'}`}
            style={{ opacity: i > step && createdProjectId ? 0.4 : 1 }}
          >
            <span className="badge-dot" />{i + 1}. {label}
          </span>
        ))}
      </div>

      {error && <div className="error">{error}</div>}

      {step === 0 && (
        <Card title="Project details">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <span style={{ fontSize: 12, color: 'var(--text-dim)', fontWeight: 600 }}>Name</span>
              <input value={form.name} onChange={e => set({ name: e.target.value })} placeholder="e.g. Example Protocol" autoFocus />
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <span style={{ fontSize: 12, color: 'var(--text-dim)', fontWeight: 600 }}>Type</span>
              <select value={form.type} onChange={e => set({ type: e.target.value })}>
                {PROJECT_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
            </label>
          </div>
        </Card>
      )}

      {step === 1 && (
        <Card title="Chains">
          <p style={{ fontSize: 12.5, color: 'var(--text-dim)', marginTop: -8, marginBottom: 14 }}>
            Select every chain this project is deployed on. You can add more later.
          </p>
          {!chainsLoaded && <div className="skeleton" style={{ height: 60, borderRadius: 10 }} />}
          {chainsLoaded && chains.length === 0 && (
            <div style={{ fontSize: 13, color: 'var(--text-dim)' }}>
              No chains configured yet — add one via the Chains page, then come back. You can skip this step for now.
            </div>
          )}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {chains.map(c => (
              <button
                key={c.id}
                className={form.chain_ids.includes(c.id) ? 'primary sm' : 'sm'}
                onClick={() => toggleChain(c.id)}
                type="button"
              >
                {c.name}
              </button>
            ))}
          </div>
        </Card>
      )}

      {step === 2 && (
        <Card title="Socials (optional)">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <input placeholder="Website URL" value={form.website} onChange={e => set({ website: e.target.value })} />
            <input placeholder="Twitter/X URL" value={form.twitter} onChange={e => set({ twitter: e.target.value })} />
            <input placeholder="Discord invite URL" value={form.discord} onChange={e => set({ discord: e.target.value })} />
          </div>
        </Card>
      )}

      {step === 3 && (
        <Card title="Task (optional)">
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, marginBottom: 14 }}>
            <input type="checkbox" checked={form.task_enabled} onChange={e => set({ task_enabled: e.target.checked })} style={{ width: 'auto' }} />
            Add a farming task now
          </label>
          {form.task_enabled && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <select value={form.task_type} onChange={e => set({ task_type: e.target.value })}>
                {TASK_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
              <select value={form.task_chain_id} onChange={e => set({ task_chain_id: e.target.value })}>
                <option value="">Select a chain…</option>
                {chains.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
              <div style={{ display: 'flex', gap: 10 }}>
                <input placeholder="Min amount" type="number" step="any" value={form.task_min_amount} onChange={e => set({ task_min_amount: e.target.value })} />
                <input placeholder="Max amount" type="number" step="any" value={form.task_max_amount} onChange={e => set({ task_max_amount: e.target.value })} />
              </div>
              <input
                placeholder="Contract address (0x…) — optional, task stays disabled until set"
                value={form.task_contract_address}
                onChange={e => set({ task_contract_address: e.target.value })}
                className="mono"
              />
              {form.task_contract_address && !isValidAddress(form.task_contract_address) && (
                <span style={{ fontSize: 12, color: 'var(--rose)' }}>Not a valid address — expecting 0x + 40 hex characters.</span>
              )}
            </div>
          )}
        </Card>
      )}

      {isCriteriaStep && (
        <Card title="Eligibility criteria (optional)">
          <p style={{ fontSize: 12.5, color: 'var(--text-dim)', marginTop: -8, marginBottom: 14 }}>
            Paste a link to the project's docs and AI will draft eligibility criteria for you to review.
            Nothing is saved until you accept the draft below.
          </p>
          <div style={{ display: 'flex', gap: 10, marginBottom: 14 }}>
            <input
              placeholder="https://docs.example.com/airdrop"
              value={form.criteria_docs_url}
              onChange={e => set({ criteria_docs_url: e.target.value })}
              style={{ flex: 1 }}
            />
            <button className="primary" onClick={fetchDraft} disabled={draftLoading || !form.criteria_docs_url.trim()}>
              {draftLoading ? 'Drafting…' : 'Draft with AI'}
            </button>
          </div>
          {draftError && <div className="error" style={{ marginBottom: 12 }}>{draftError}</div>}
          {draft && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div style={{ fontSize: 12.5, color: 'var(--text-dim)' }}>
                AI agreement: {draft.agreement_score}%
                {draft.requires_human && <span style={{ marginLeft: 8 }}><Badge status="pending">needs your review</Badge></span>}
              </div>
              {draft.draft_criteria.length === 0 ? (
                <div style={{ fontSize: 13, color: 'var(--text-dim)' }}>No criteria could be extracted from that page.</div>
              ) : (
                draft.draft_criteria.map((c, i) => (
                  <div key={i} style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)', borderRadius: 8, padding: '10px 12px', fontSize: 13 }}>
                    <div style={{ fontWeight: 600 }}>[{c.type}] {c.description}</div>
                    {c.threshold != null && <div style={{ color: 'var(--text-dim)', fontSize: 12 }}>Threshold: {c.threshold} {c.unit || ''}</div>}
                    {c.uncertain && <span style={{ fontSize: 11, color: 'var(--amber)' }}>⚠ uncertain</span>}
                  </div>
                ))
              )}
              {draft.draft_criteria.length > 0 && (
                <button className="primary" onClick={acceptDraft} disabled={submitting} style={{ alignSelf: 'flex-start' }}>
                  Accept and save {draft.draft_criteria.length} criteria
                </button>
              )}
            </div>
          )}
          <button className="ghost sm" style={{ marginTop: 14 }} onClick={() => navigate('/projects')}>
            Skip — I'll add criteria later
          </button>
        </Card>
      )}

      {isReview && (
        <Card title="Review">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, fontSize: 13.5 }}>
            <div><strong>{form.name}</strong> — {form.type}</div>
            <div>Chains: {form.chain_ids.length ? chains.filter(c => form.chain_ids.includes(c.id)).map(c => c.name).join(', ') : 'none selected'}</div>
            {form.website && <div>Website: {form.website}</div>}
            {form.twitter && <div>Twitter: {form.twitter}</div>}
            {form.discord && <div>Discord: {form.discord}</div>}
            {form.task_enabled && form.task_type && (
              <div>
                Task: {form.task_type} on chain #{form.task_chain_id} ({form.task_min_amount}–{form.task_max_amount})
                {!form.task_contract_address && ' — will be created disabled until a contract is added'}
              </div>
            )}
            <div style={{ color: 'var(--text-dim)', fontSize: 12.5 }}>After creating, you'll be offered an optional AI-drafted criteria step.</div>
          </div>
        </Card>
      )}

      {!isCriteriaStep && (
        <div style={{ display: 'flex', gap: 10, justifyContent: 'space-between' }}>
          <button className="ghost" onClick={step === 0 ? () => navigate('/projects') : back} disabled={submitting}>
            {step === 0 ? 'Cancel' : 'Back'}
          </button>
          {isReview ? (
            <button className="primary" onClick={createProject} disabled={submitting}>
              {submitting ? 'Creating…' : createdProjectId ? 'Retry adding task' : 'Create project'}
            </button>
          ) : (
            <button className="primary" onClick={next}>Next</button>
          )}
        </div>
      )}
    </div>
  )
}
