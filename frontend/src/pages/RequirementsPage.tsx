import { CheckOutlined, ReloadOutlined, RobotOutlined, UploadOutlined } from '@ant-design/icons'
import { Alert, Button, Drawer, Empty, Form, Input, List, message, Space, Steps, Table, Tag, Typography, Upload } from 'antd'
import { useEffect, useState } from 'react'

import { api } from '../api'
import { useSession } from '../store'

type PageResult<T> = { items: T[]; total: number }
type Review = { id: string; requirement_module_id: string; status: string; revision: number; ambiguities: string[]; acceptance_suggestions: string[]; test_points?: TestPoint[]; error_message?: string }
type TestPoint = { id: string; stable_key: string; title: string; risk: string; preconditions: string[]; test_data_refs: string[]; expected_result: string }
type Coverage = { id: string; test_point_id: string; scenario_type: string; scenario_id: string; status: string }

const color: Record<string, string> = { approved: 'green', rejected: 'red', pending_review: 'gold', generating: 'blue', PASSED: 'green', FAILED: 'red', NEEDS_REVIEW: 'orange' }

export function RequirementsPage() {
  const projectId = useSession((state) => state.projectId)
  const [detail, setDetail] = useState<any>()
  const [documentId, setDocumentId] = useState('')
  const [reviews, setReviews] = useState<Review[]>([])
  const [coverages, setCoverages] = useState<Coverage[]>([])
  const [selectedReview, setSelectedReview] = useState<Review>()
  const [loading, setLoading] = useState(false)

  const refreshReviews = async () => {
    if (!projectId) return
    const [reviewRows, coverageRows] = await Promise.all([
      api<PageResult<Review>>({ url: `/projects/${projectId}/ai/requirement-reviews` }),
      api<PageResult<Coverage>>({ url: `/projects/${projectId}/ai/requirement-coverages` }),
    ])
    setReviews(reviewRows.items)
    setCoverages(coverageRows.items)
  }
  const refreshDocument = async (id = documentId) => {
    if (!projectId || !id) return
    setDetail(await api({ url: `/projects/${projectId}/requirements/${id}` }))
    setDocumentId(id)
  }
  useEffect(() => { void refreshReviews().catch((error: Error) => message.error(error.message)) }, [projectId])
  useEffect(() => {
    if (!reviews.some((review) => review.status === 'generating')) return
    const timer = window.setInterval(() => void refreshReviews(), 3000)
    return () => window.clearInterval(timer)
  }, [reviews, projectId])

  if (!projectId) return <Empty description="请先选择项目" />

  const requestReview = async (moduleId: string) => {
    setLoading(true)
    try {
      await api({ method: 'post', url: `/projects/${projectId}/ai/requirement-reviews`, data: { requirement_module_id: moduleId } })
      message.success('可测性评审已进入队列')
      await refreshReviews()
    } catch (error) { message.error((error as Error).message) } finally { setLoading(false) }
  }
  const openReview = async (review: Review) => {
    try { setSelectedReview(await api<Review>({ url: `/projects/${projectId}/ai/requirement-reviews/${review.id}` })) }
    catch (error) { message.error((error as Error).message) }
  }
  const decide = async (review: Review, decision: 'approved' | 'rejected') => {
    try {
      await api({ method: 'post', url: `/projects/${projectId}/ai/requirement-reviews/${review.id}/decision`, data: { decision } })
      setSelectedReview(undefined)
      await refreshReviews()
    } catch (error) { message.error((error as Error).message) }
  }

  return <Space direction="vertical" className="page-block" size="large">
    <Space className="page-title"><div><Typography.Title level={3}>需求与可测性评审</Typography.Title><Typography.Text type="secondary">AI 输出先进入候选审核，批准的测试点才能参与覆盖追踪。</Typography.Text></div><Button icon={<ReloadOutlined />} onClick={() => void refreshReviews()}>刷新</Button></Space>
    <Upload showUploadList={false} customRequest={async ({ file, onSuccess, onError }) => {
      const form = new FormData(); form.append('file', file as Blob)
      try { const data: any = await api({ method: 'post', url: `/projects/${projectId}/requirements/upload`, data: form }); await refreshDocument(data.document_id); onSuccess?.(data); message.success('已进入解析队列') }
      catch (error) { onError?.(error as Error) }
    }}><Button icon={<UploadOutlined />}>上传需求文档</Button></Upload>
    {documentId && <Space><Input value={documentId} readOnly /><Button onClick={() => void refreshDocument()}>刷新文档</Button></Space>}
    {detail ? <>
      <Steps items={[{ title: '上传', status: 'finish' }, { title: '解析', status: detail.versions[0].parse_status === 'completed' ? 'finish' : 'process' }, { title: '确认模块', status: detail.modules.some((item: any) => item.status === 'confirmed') ? 'finish' : 'wait' }]} />
      <Table rowKey="id" dataSource={detail.modules} columns={[{ title: '模块', dataIndex: 'name' }, { title: '状态', dataIndex: 'status', render: (value) => <Tag>{value}</Tag> }, { title: '来源块', dataIndex: 'source_block_ids', render: (value) => value.length }, { title: '操作', render: (_, row: any) => <Space><Button disabled={!row.source_block_ids.length || row.status === 'confirmed'} onClick={async () => { await api({ method: 'post', url: `/projects/${projectId}/requirement-modules/${row.id}/confirm` }); await refreshDocument() }}>确认模块</Button><Button icon={<RobotOutlined />} loading={loading} disabled={row.status !== 'confirmed'} onClick={() => void requestReview(row.id)}>AI 评审</Button></Space> }]} />
    </> : <Empty description="上传后查看需求模块" />}

    <Typography.Title level={4}>可测性评审候选</Typography.Title>
    <Table rowKey="id" dataSource={reviews} locale={{ emptyText: '暂无 AI 评审' }} columns={[{ title: '需求模块', dataIndex: 'requirement_module_id' }, { title: 'Revision', dataIndex: 'revision' }, { title: '状态', dataIndex: 'status', render: (value) => <Tag color={color[value]}>{value}</Tag> }, { title: '错误', dataIndex: 'error_message' }, { title: '操作', render: (_, row) => <Button onClick={() => void openReview(row)}>查看评审</Button> }]} />
    <Typography.Title level={4}>需求覆盖</Typography.Title>
    <Table rowKey="id" dataSource={coverages} locale={{ emptyText: '暂无场景覆盖关联' }} columns={[{ title: '测试点', dataIndex: 'test_point_id' }, { title: '类型', dataIndex: 'scenario_type' }, { title: '场景', dataIndex: 'scenario_id' }, { title: '状态', dataIndex: 'status', render: (value) => <Tag color={color[value]}>{value}</Tag> }]} />

    <Drawer open={Boolean(selectedReview)} title="可测性评审" width={680} onClose={() => setSelectedReview(undefined)}>
      {selectedReview?.status === 'pending_review' && <Alert type="warning" showIcon message="候选内容尚未批准" action={<Space><Button danger onClick={() => void decide(selectedReview, 'rejected')}>驳回</Button><Button type="primary" icon={<CheckOutlined />} onClick={() => void decide(selectedReview, 'approved')}>批准</Button></Space>} />}
      <List header="测试点" dataSource={selectedReview?.test_points || []} renderItem={(item) => <List.Item><List.Item.Meta title={<Space>{item.title}<Tag>{item.risk}</Tag></Space>} description={<Space direction="vertical"><span>{item.expected_result}</span><span>前置条件：{item.preconditions.join('；') || '-'}</span><span>数据引用：{item.test_data_refs.join('；') || '-'}</span></Space>} /></List.Item>} />
      <List header="需求歧义" dataSource={selectedReview?.ambiguities || []} renderItem={(item) => <List.Item>{item}</List.Item>} />
      <List header="验收建议" dataSource={selectedReview?.acceptance_suggestions || []} renderItem={(item) => <List.Item>{item}</List.Item>} />
    </Drawer>
  </Space>
}
