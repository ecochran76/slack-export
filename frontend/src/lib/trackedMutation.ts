export type MutationStatus = "busy" | "success" | "error";

export type MutationState = {
  message: string;
  status: MutationStatus;
};

export type MutationStateMap = Record<string, MutationState>;

type MutationStateSetter = (updater: (current: MutationStateMap) => MutationStateMap) => void;

export type TrackedMutationOptions<Response> = {
  afterSettled?: () => Promise<void> | void;
  busyMessage: string;
  errorMessage: (error: unknown) => string;
  key: string;
  run: () => Promise<Response>;
  setMutations: MutationStateSetter;
  successMessage: (response: Response) => string;
};

export async function runTrackedMutation<Response>({
  afterSettled,
  busyMessage,
  errorMessage,
  key,
  run,
  setMutations,
  successMessage
}: TrackedMutationOptions<Response>): Promise<Response | undefined> {
  setMutations((current) => ({
    ...current,
    [key]: {
      message: busyMessage,
      status: "busy"
    }
  }));

  try {
    const response = await run();
    setMutations((current) => ({
      ...current,
      [key]: {
        message: successMessage(response),
        status: "success"
      }
    }));
    return response;
  } catch (error) {
    setMutations((current) => ({
      ...current,
      [key]: {
        message: errorMessage(error),
        status: "error"
      }
    }));
    return undefined;
  } finally {
    await afterSettled?.();
  }
}
