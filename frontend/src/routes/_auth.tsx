import { createFileRoute, Outlet, Navigate } from '@tanstack/react-router';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { WorkbenchLayout } from '@/layouts/WorkbenchLayout';

/**
 * Protected layout route component (AuthGuard)
 * 
 * Wraps protected routes and ensures user is authenticated.
 * Redirects to login if not authenticated.
 * Renders WorkbenchLayout with sidebar, header, and nested routes.
 */
const AuthLayout = () => {
  const { isAuthenticated, accessToken } = useAuth();

  // Redirect to login if not authenticated
  if (!isAuthenticated || !accessToken) {
    return <Navigate to="/login" />;
  }

  // Render protected layout with workbench
  return (
    <WorkbenchLayout>
      <Outlet />
    </WorkbenchLayout>
  );
};

/**
 * Protected layout route definition
 */
export const Route = createFileRoute('/_auth')({
  component: AuthLayout,
});
