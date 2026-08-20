import type { JobInfo } from '@/api/jobs'

/**
 * Visual preview fixture only. Production pages continue to use the jobs API.
 * Keeping the fixture typed prevents the public preview from drifting away
 * from the backend contract used by the real job picker.
 */
export const previewJobs: JobInfo[] = [
  {
    id: 'preview-frontend',
    job_title: '前端开发工程师',
    description: '构建高性能、体验稳定的 Web 产品与交互。',
    required_skills: ['HTML/CSS', 'JavaScript', 'Vue/React', '工程化'],
  },
  {
    id: 'preview-backend',
    job_title: '后端开发工程师',
    description: '设计稳定可扩展的服务与高质量业务系统。',
    required_skills: ['Python/Java', '数据库', 'API 设计', '系统设计'],
  },
  {
    id: 'preview-operations',
    job_title: '运维工程师',
    description: '保障系统高可用、安全与自动化运维。',
    required_skills: ['Linux', '容器', '监控', '自动化'],
  },
  {
    id: 'preview-product',
    job_title: '产品经理',
    description: '洞察用户需求，定义产品价值并推动落地。',
    required_skills: ['需求分析', '产品设计', '数据意识', '项目推进'],
  },
]
