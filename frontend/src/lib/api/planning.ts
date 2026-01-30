/**
 * Phase 5: Implementation Planner - API Client
 */

import { apiClient } from '@/core/api/client';
import type { Plan, Task } from '@/types/planner';

export interface GeneratePlanRequest {
  task_description: string;
  context?: {
    existing_modules?: string[];
    constraints?: string[];
  };
  max_steps?: number;
}

export interface GeneratePlanResponse {
  plan_id: string;
  task_description: string;
  steps: Array<{
    step_number: number;
    description: string;
    dependencies: number[];
    estimated_effort: string;
  }>;
  status: 'draft' | 'refined' | 'approved' | 'rejected';
  created_at: string;
}

export interface RefinePlanRequest {
  feedback: string;
  context_updates?: Record<string, unknown>;
}

/**
 * Generate a new implementation plan
 */
export async function generatePlan(request: GeneratePlanRequest): Promise<Plan> {
  const response = await apiClient.post<GeneratePlanResponse>(
    '/api/planning/generate',
    request
  );

  return transformPlanResponse(response.data);
}

/**
 * Refine an existing plan with feedback
 */
export async function refinePlan(
  planId: string,
  request: RefinePlanRequest
): Promise<Plan> {
  const response = await apiClient.put<GeneratePlanResponse>(
    `/api/planning/${planId}/refine`,
    request
  );

  return transformPlanResponse(response.data);
}

/**
 * Get a specific plan by ID
 */
export async function getPlan(planId: string): Promise<Plan> {
  const response = await apiClient.get<GeneratePlanResponse>(
    `/api/planning/${planId}`
  );

  return transformPlanResponse(response.data);
}

/**
 * Transform API response to frontend Plan type
 */
function transformPlanResponse(response: GeneratePlanResponse): Plan {
  const tasks: Task[] = response.steps.map((step) => ({
    id: `${response.plan_id}-task-${step.step_number}`,
    planId: response.plan_id,
    title: step.description,
    description: step.estimated_effort,
    completed: false,
    order: step.step_number,
    links: [],
    details: step.dependencies.map((dep) => ({
      id: `detail-${dep}`,
      type: 'dependency',
      title: `Depends on step ${dep}`,
      content: '',
      order: dep,
    })),
    createdAt: new Date(response.created_at),
    updatedAt: new Date(response.created_at),
  }));

  return {
    id: response.plan_id,
    name: response.task_description,
    description: response.task_description,
    createdAt: new Date(response.created_at),
    updatedAt: new Date(response.created_at),
    tasks,
    metadata: {
      totalTasks: tasks.length,
      completedTasks: 0,
      progress: 0,
    },
  };
}
