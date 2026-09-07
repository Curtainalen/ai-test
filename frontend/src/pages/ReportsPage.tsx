import { ReloadOutlined } from '@ant-design/icons'
import { Button, Card, Drawer, Empty, Select, Space, Statistic, Table, Tag, Tooltip, Typography } from 'antd'
import { useCallback, useEffect, useState } from 'react'

import { api } from '../api'
import { useSession } from '../store'

type Report = {
  id: string
  report_type: 'api' | 'ui'
  execution_id: string
  status: string
  summary: { total?: number }
  scenario: { name?: string }
  environment: { name?: string }
  finished_at?: string
}

type ReportPage = { items: Report[]; total: number }
type ReportTypeFilter = 'all' | 'api' | 'ui'
type ReportStatusFilter = 'all' | 'passed' | 'failed' | 'canceled'
type ReportCounts = { total: number; passed: number; failed: number; canceled: number; pass_rate: number | null }
type ReportSummary = {
  overview: ReportCounts
  by_type: Record<'api' | 'ui', ReportCounts>
  trend: Array<ReportCounts & { date: string }>
  failure_categories: Array<{ category: string; count: number }>
}

const statusColor: Record<string, string> = { passed: 'green', failed: 'red', canceled: 'default' }

export function ReportsPage() {
  const projectId = useSession((state) => state.projectId)
  const [rows, setRows] = useState<Report[]>([])
  const [summary, setSummary] = useState<ReportSummary>()
  const [detail, setDetail] = useState<unknown>()
  const [reportType, setReportType] = useState<ReportTypeFilter>('all')
  const [status, setStatus] = useState<ReportStatusFilter>('all')
  const [page, setPage] = useState(1)
  const pageSize = 10

  const load = useCallback(async () => {
    if (!projectId) return
    const params = {
      ...(reportType === 'all' ? {} : { report_type: reportType }),
      ...(status === 'all' ? {} : { status }),
      page,
      page_size: pageSize,
    }
    const [reportPage, reportSummary] = await Promise.all([
      api<ReportPage>({ url: `/projects/${projectId}/reporting/reports`, params }),
      api<ReportSummary>({ url: `/projects/${projectId}/reporting/summary`, params }),
    ])
    setRows(reportPage.items)
    setSummary(reportSummary)
  }, [projectId, reportType, status, page])

  useEffect(() => { void load() }, [load])

  if (!projectId) return <Empty description="请先选择项目" />

  const overview = summary?.overview
  const typeCounts = summary?.by_type
  return <Space direction="vertical" size="large" className="page-block">
    <Space className="page-title">
      <div><Typography.Title level={3}>综合执行报告</Typography.Title><Typography.Text type="secondary">统一查看 API 与 UI 自动化的执行结果、趋势和失败分布。</Typography.Text></div>
      <Space>
        <Select aria-label="报告类型" value={reportType} onChange={(value) => { setPage(1); setReportType(value as ReportTypeFilter) }} style={{ width: 130 }} options={[{ value: 'all', label: '全部类型' }, { value: 'api', label: 'API' }, { value: 'ui', label: 'UI' }]} />
        <Select aria-label="报告状态" value={status} onChange={(value) => { setPage(1); setStatus(value as ReportStatusFilter) }} style={{ width: 130 }} options={[{ value: 'all', label: '全部状态' }, { value: 'passed', label: '通过' }, { value: 'failed', label: '失败' }, { value: 'canceled', label: '已取消' }]} />
        <Tooltip title="刷新报告"><Button aria-label="刷新报告" icon={<ReloadOutlined />} onClick={() => void load()} /></Tooltip>
      </Space>
    </Space>
    <div className="report-summary-grid">
      <Card size="small"><Statistic title="执行报告" value={overview?.total || 0} /></Card>
      <Card size="small"><Statistic title="通过" value={overview?.passed || 0} valueStyle={{ color: '#389e0d' }} /></Card>
      <Card size="small"><Statistic title="失败" value={overview?.failed || 0} valueStyle={{ color: '#cf1322' }} /></Card>
      <Card size="small"><Statistic title="通过率" value={overview?.pass_rate ?? '-'} suffix={overview?.pass_rate === null ? undefined : '%'} /></Card>
    </div>
    <div className="report-type-summary-grid">
      <Card size="small"><Statistic title="API 报告" value={typeCounts?.api.total || 0} suffix={`通过 ${typeCounts?.api.passed || 0}`} /></Card>
      <Card size="small"><Statistic title="UI 报告" value={typeCounts?.ui.total || 0} suffix={`通过 ${typeCounts?.ui.passed || 0}`} /></Card>
      <Card size="small"><Statistic title="失败分类" value={summary?.failure_categories?.length || 0} suffix="类" /></Card>
    </div>
    <Card size="small" title="报告明细">
      <Table rowKey={(row) => `${row.report_type}:${row.id}`} dataSource={rows} pagination={{ current: page, pageSize, total: reportPageTotal(rows, summary), onChange: setPage, showSizeChanger: false }} locale={{ emptyText: '尚无执行报告' }} columns={[
      { title: '类型', dataIndex: 'report_type', render: (value) => <Tag color={value === 'api' ? 'blue' : 'purple'}>{value.toUpperCase()}</Tag> },
      { title: '场景', render: (_, row) => row.scenario?.name || '-' },
      { title: '环境', render: (_, row) => row.environment?.name || '-' },
      { title: '状态', dataIndex: 'status', render: (value) => <Tag color={statusColor[value] || 'default'}>{value}</Tag> },
      { title: '步骤', render: (_, row) => row.summary?.total ?? 0 },
      { title: '完成时间', dataIndex: 'finished_at', render: (value) => value || '-' },
      { title: '操作', render: (_, row) => <Button onClick={async () => setDetail(await api({ url: `/projects/${projectId}/reporting/reports/${row.report_type}/${row.id}` }))}>详情</Button> },
      ]} />
    </Card>
    <div className="report-insight-grid">
      <Card size="small" title="执行趋势"><Table rowKey="date" size="small" pagination={false} dataSource={summary?.trend || []} columns={[{ title: '日期', dataIndex: 'date' }, { title: '总数', dataIndex: 'total' }, { title: '通过', dataIndex: 'passed' }, { title: '失败', dataIndex: 'failed' }, { title: '通过率', render: (_, row) => row.pass_rate === null ? '-' : `${row.pass_rate}%` }]} /></Card>
      <Card size="small" title="失败分类"><Table rowKey="category" size="small" pagination={false} dataSource={summary?.failure_categories || []} columns={[{ title: '分类', dataIndex: 'category' }, { title: '次数', dataIndex: 'count' }]} /></Card>
    </div>
    <Drawer width={760} open={Boolean(detail)} onClose={() => setDetail(undefined)} title="报告证据"><pre className="result-panel">{JSON.stringify(detail, null, 2)}</pre></Drawer>
  </Space>
}

function reportPageTotal(rows: Report[], summary?: ReportSummary) {
  if (!summary) return rows.length
  return summary.overview.total
}
