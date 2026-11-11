import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import {
  TestResultCard,
  type TestResultCardProps,
} from "../../../src/components/systems/sandbox/components/test-run-result";
import { VerifiedWorkspaceIdentityProvider } from "../../../src/components/systems/shared/runtime/workspace-identity";
import { UserPreferencesProvider } from "../../../src/components/theme-provider";

/**
 * A Test result card inside the providers the signed-in shell gives it: one
 * account, its query cache, and its preferences. No workspace region is
 * cached, so dates (none in these cases) would read in the default format.
 */
export function TestResultCardHarness(props: TestResultCardProps) {
  return (
    <QueryClientProvider client={new QueryClient()}>
      <VerifiedWorkspaceIdentityProvider userId="00000000-0000-4000-8000-000000000001">
        <UserPreferencesProvider>
          <TestResultCard {...props} />
        </UserPreferencesProvider>
      </VerifiedWorkspaceIdentityProvider>
    </QueryClientProvider>
  );
}
