/**
 * Phase 5: Planner Page Component
 */

import { useEffect } from 'react';
import { ClipboardList, FileText } from 'lucide-react';
import { PlanInput } from './PlanInput';
import { ProgressBar } from './ProgressBar';
import { TaskList } from './TaskList';
import { usePlannerStore } from '@/stores/planner';
import { generatePlan } from '@/lib/api/planning';
import { DEMO_MODE } from '@/lib/demo/config';
import { demoPlan } from '@/lib/demo/plannerData';
import type { Plan } from '@/types/planner';

export function PlannerPage() {
  const {
    currentPlan,
    isGenerating,
    error,
    setCurrentPlan,
    addPlan,
    toggleTask,
    addTask,
    removeTask,
    setGenerating,
    setError,
  } = usePlannerStore();

  // Load demo plan in demo mode
  useEffect(() => {
    if (DEMO_MODE && !currentPlan) {
      setCurrentPlan(demoPlan);
    }
  }, []);

  const handleGeneratePlan = async (description: string) => {
    setGenerating(true);
    setError(null);

    try {
      if (DEMO_MODE) {
        // Simulate API delay
        await new Promise((resolve) => setTimeout(resolve, 2000));
        
        // Generate a simple demo plan
        const newPlan: Plan = {
          id: `plan-${Date.now()}`,
          name: description.slice(0, 50),
          description,
          createdAt: new Date(),
          updatedAt: new Date(),
          tasks: [
            {
              id: `task-${Date.now()}-1`,
              planId: `plan-${Date.now()}`,
              title: 'Research and planning',
              description: 'Research best practices and create implementation plan',
              completed: false,
              order: 1,
              links: [],
              details: [],
              createdAt: new Date(),
              updatedAt: new Date(),
            },
            {
              id: `task-${Date.now()}-2`,
              planId: `plan-${Date.now()}`,
              title: 'Set up project structure',
              description: 'Create necessary files and folders',
              completed: false,
              order: 2,
              links: [],
              details: [],
              createdAt: new Date(),
              updatedAt: new Date(),
            },
            {
              id: `task-${Date.now()}-3`,
              planId: `plan-${Date.now()}`,
              title: 'Implement core functionality',
              description: 'Build the main features',
              completed: false,
              order: 3,
              links: [],
              details: [],
              createdAt: new Date(),
              updatedAt: new Date(),
            },
            {
              id: `task-${Date.now()}-4`,
              planId: `plan-${Date.now()}`,
              title: 'Write tests',
              description: 'Add unit and integration tests',
              completed: false,
              order: 4,
              links: [],
              details: [],
              createdAt: new Date(),
              updatedAt: new Date(),
            },
            {
              id: `task-${Date.now()}-5`,
              planId: `plan-${Date.now()}`,
              title: 'Documentation',
              description: 'Write documentation and examples',
              completed: false,
              order: 5,
              links: [],
              details: [],
              createdAt: new Date(),
              updatedAt: new Date(),
            },
          ],
          metadata: {
            totalTasks: 5,
            completedTasks: 0,
            progress: 0,
          },
        };

        addPlan(newPlan);
      } else {
        // Use real API
        const plan = await generatePlan({
          task_description: description,
          max_steps: 10,
        });
        addPlan(plan);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate plan');
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="border-b p-4">
        <div className="flex items-center gap-2">
          <ClipboardList className="h-5 w-5" />
          <h1 className="text-2xl font-bold">Implementation Planner</h1>
        </div>
        <p className="mt-1 text-sm text-muted-foreground">
          AI-powered task breakdown and progress tracking
        </p>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto p-6">
        <div className="mx-auto max-w-4xl space-y-6">
          {/* Error Message */}
          {error && (
            <div className="rounded-lg border border-red-500 bg-red-50 p-4 text-sm text-red-900 dark:bg-red-950 dark:text-red-100">
              {error}
            </div>
          )}

          {/* Plan Input */}
          {!currentPlan && (
            <div className="rounded-lg border bg-card p-6">
              <PlanInput onGenerate={handleGeneratePlan} isLoading={isGenerating} />
            </div>
          )}

          {/* Current Plan */}
          {currentPlan && (
            <>
              {/* Plan Header */}
              <div className="rounded-lg border bg-card p-6">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <h2 className="text-xl font-bold">{currentPlan.name}</h2>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {currentPlan.description}
                    </p>
                  </div>
                  <FileText className="h-5 w-5 text-muted-foreground" />
                </div>
                
                <div className="mt-6">
                  <ProgressBar
                    completed={currentPlan.metadata.completedTasks}
                    total={currentPlan.metadata.totalTasks}
                  />
                </div>
              </div>

              {/* Task List */}
              <TaskList
                tasks={currentPlan.tasks}
                planId={currentPlan.id}
                onTaskToggle={toggleTask}
                onTaskRemove={removeTask}
                onTaskAdd={addTask}
              />
            </>
          )}

          {/* Empty State */}
          {!currentPlan && !isGenerating && (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <div className="rounded-full bg-muted p-6 mb-4">
                <ClipboardList className="h-12 w-12 text-muted-foreground" />
              </div>
              <h3 className="text-lg font-semibold mb-2">No implementation plan yet</h3>
              <p className="text-sm text-muted-foreground max-w-sm">
                Describe what you want to build and I'll break it down into actionable steps
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
