"use client";
import { useWorkspaceDisplayRegion } from "@/components/use-display-region";

import { useCallback, useId, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link2, Send, X } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { DisabledReason } from "@/components/ui/disabled-reason";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { FieldLegend, FieldSet } from "@/components/ui/field";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { toast } from "@/components/ui/toast";
import { useVerifiedWorkspaceUserId } from "@/components/systems/shared/runtime/workspace-identity";

import {
  afterAccessUserChange,
  invitationSettingsOptions,
} from "../adapters/access-queries";
import {
  defaultGuestDays,
  emailError,
  formatDate,
  GUEST_DAYS_MAX,
  GUEST_DAYS_MIN,
  guestDaysError,
  guestExpiryFromDays,
  invitationMadeByLostInvite,
  isUnansweredRequest,
  peopleErrorMessage,
  roleLabels,
  usernameError,
  usernameFromEmail,
} from "../helpers/people";
import { ApiError } from "@/lib/api";
import {
  inviteAccessUser,
  listAccessUsers,
  type AccessInvitationCreate,
  type AccessUserRole,
} from "../state/api";
import {
  useAccessDraftRegistration,
  useAccessVerifying,
  verifyingReason,
} from "../state/draft-navigation";
import { inviteDraftJournal, type InviteDraft } from "../state/form-drafts";
import { SponsorSearchSelect } from "./person-search-select";
import { useAccessCatalog, catalogGroups } from "../hooks/use-access-catalog";
import { groupAccessLine } from "../helpers/add-access";
import { Input } from "@/components/ui/input";
import { ActionError } from "./editor-conflicts";
import { DiscardChangesDialog, SelectField, TextField } from "./people-fields";
import { useErrorText } from "@/lib/use-error-text";
import { ErrorReference } from "@/components/ui/error-reference";
import { apiErrorReference } from "@/lib/api-errors";
import { emailSetupStatusOptions } from "@/components/systems/manage/adapters/manage-queries";
import { emailNotSetUp } from "@/components/systems/manage/domain/email-setup-rules";
import { OneTimeSecret } from "./one-time-secret";

type InviteForm = InviteDraft;
type Delivery = "email" | "link";

const deliveryChoices: readonly {
  value: Delivery;
  label: string;
  line: string;
}[] = [
  // The names hold no "email", so the Email field keeps its one label.
  {
    value: "email",
    label: "Send from Slate Operations",
    line: "An invitation email goes to their address.",
  },
  {
    value: "link",
    label: "Copy a link to send yourself",
    line: "Send it by any channel. It works once, for 24 hours.",
  },
];

const emptyForm: InviteForm = {
  email: "",
  username: null,
  display_name: "",
  job_title: "",
  role: "member",
  group_ids: [],
  sponsor_user_id: "",
  days: null,
};

function isEmpty(form: InviteForm): boolean {
  return (
    form.email === "" &&
    form.username === null &&
    form.display_name === "" &&
    form.job_title === "" &&
    form.role === "member" &&
    form.group_ids.length === 0 &&
    form.sponsor_user_id === "" &&
    form.days === null
  );
}

/** Whether an unsent invitation is kept in this tab's journal. */
export function hasKeptInvitation(userId: string): boolean {
  return inviteDraftJournal.read(userId) !== null;
}

type FieldErrors = Partial<
  Record<"email" | "username" | "sponsor" | "days", string>
>;

const roleDescriptions: Record<AccessUserRole, string> = {
  // A member's access comes from the groups below, which say so.
  member: "",
  guest: "Can only read, for a limited time, with a sponsor.",
  admin: "Has full access everywhere and can change people and groups.",
};

export function InvitePersonDialog({
  open,
  onOpenChange,
  onFound,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Opens the person an invitation made when its answer was lost. */
  onFound: (userId: string) => void;
}) {
  const id = useId();
  const region = useWorkspaceDisplayRegion();
  const client = useQueryClient();
  const signedInId = useVerifiedWorkspaceUserId();
  const settings = useQuery({ ...invitationSettingsOptions(), enabled: open });
  // An unsent invitation comes back from the journal, for example after
  // Back and Forward.
  const [form, setForm] = useState<InviteForm>(
    () => inviteDraftJournal.read(signedInId) ?? emptyForm,
  );
  const [discardError, setDiscardError] = useState("");
  const verifying = useAccessVerifying();
  const [errors, setErrors] = useState<FieldErrors>({});
  const [submitErrorFailure, setSubmitError] = useErrorText();
  const submitError = submitErrorFailure?.message ?? "";
  const [pending, setPending] = useState(false);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const [now] = useState(() => Date.now());
  // DEC-0042: with email not set up, a copied link is the only delivery.
  const emailStatus = useQuery({ ...emailSetupStatusOptions(), enabled: open });
  const linkOnly = emailNotSetUp(emailStatus.data);
  const [chosenDelivery, setChosenDelivery] = useState<Delivery>("email");
  const delivery: Delivery = linkOnly ? "link" : chosenDelivery;
  // The link the server made, shown once until the dialog closes.
  const [created, setCreated] = useState<{
    email: string;
    url: string;
  } | null>(null);

  const username = form.username ?? usernameFromEmail(form.email);
  const days = form.days ?? defaultGuestDays(settings.data);
  const dirty = !isEmpty(form);
  const groupSearch = useAccessCatalog({
    kind: "groups",
    selectedIds: form.group_ids,
    enabled: open && form.role !== "admin",
  });
  const groups = catalogGroups(groupSearch.combined);
  const guestEnds = guestExpiryFromDays(days, new Date(now));

  const reset = useCallback(() => {
    setForm(emptyForm);
    setChosenDelivery("email");
    setErrors({});
    setSubmitError("");
    setDiscardError("");
    setConfirmDiscard(false);
  }, []);
  const discard = useCallback(() => {
    if (!inviteDraftJournal.discard(signedInId)) return false;
    reset();
    onOpenChange(false);
    return true;
  }, [onOpenChange, reset, signedInId]);
  useAccessDraftRegistration("person-invite", {
    dirty: open && dirty,
    discard,
    pending,
  });

  function update(patch: Partial<InviteForm>) {
    const next = { ...form, ...patch };
    setForm(next);
    setSubmitError("");
    if (isEmpty(next)) inviteDraftJournal.discard(signedInId);
    else inviteDraftJournal.write(signedInId, next);
  }

  function requestClose() {
    if (pending) return;
    if (created) {
      setCreated(null);
      onOpenChange(false);
      return;
    }
    if (dirty) {
      setDiscardError("");
      setConfirmDiscard(true);
    } else discard();
  }

  /**
   * After a lost answer, the invitation may exist. Opens it when it does;
   * otherwise the person may try again.
   */
  async function findLostInvitation(email: string): Promise<string> {
    try {
      const page = await listAccessUsers({
        search: email,
        status: "pending",
        limit: 25,
        offset: 0,
      });
      const made = invitationMadeByLostInvite(page.items, email);
      if (!made) return "The invitation could not be sent. Try again.";
      inviteDraftJournal.discard(signedInId);
      toast.add({
        title: "Invitation found. It was sent before the connection dropped.",
        type: "info",
      });
      reset();
      onOpenChange(false);
      onFound(made.id);
      void afterAccessUserChange(client);
      return "";
    } catch {
      return "The invitation may have been sent. Check People before you try again.";
    }
  }

  function validate(): FieldErrors {
    const next: FieldErrors = {};
    const email = emailError(form.email);
    if (email) next.email = email;
    const name = usernameError(username);
    if (name) next.username = name;
    if (form.role === "guest") {
      if (!form.sponsor_user_id) next.sponsor = "Choose a sponsor.";
      const length = guestDaysError(days);
      if (length) next.days = length;
    }
    return next;
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending || verifying) return;
    const found = validate();
    setErrors(found);
    if (Object.keys(found).length) return;
    const request: AccessInvitationCreate = {
      email: form.email.trim(),
      username: username.trim(),
      role: form.role,
      ...(form.display_name.trim()
        ? { display_name: form.display_name.trim() }
        : {}),
      ...(form.job_title.trim() ? { job_title: form.job_title.trim() } : {}),
      ...(form.role !== "admin" && form.group_ids.length
        ? { group_ids: form.group_ids }
        : {}),
      ...(form.role === "guest"
        ? {
            sponsor_user_id: form.sponsor_user_id,
            expires_at: guestExpiryFromDays(days, new Date()),
          }
        : {}),
      // Email is the server's default, so only a link is named.
      ...(delivery === "link" ? { delivery } : {}),
    };
    setPending(true);
    setSubmitError("");
    try {
      const response = await inviteAccessUser(request);
      if (response.invitation_url) {
        inviteDraftJournal.discard(signedInId);
        reset();
        setCreated({
          email: response.user.email,
          url: response.invitation_url,
        });
        void afterAccessUserChange(client);
        return;
      }
      toast.add({
        title: "Invitation sent",
        description:
          response.delivery === "in_app"
            ? `${response.user.email} can accept this invitation when signed in.`
            : `An invitation email is on its way to ${response.user.email}.`,
        type: "success",
      });
      inviteDraftJournal.discard(signedInId);
      reset();
      onOpenChange(false);
      void afterAccessUserChange(client);
    } catch (error) {
      if (isUnansweredRequest(error)) {
        setSubmitError(await findLostInvitation(request.email), error);
        return;
      }
      setSubmitError(
        error instanceof ApiError && error.status === 502
          ? "The invitation email could not be sent. Try again."
          : peopleErrorMessage(
              error,
              "The invitation could not be sent. Try again.",
            ),
        error,
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <>
      <Dialog
        open={open}
        onOpenChange={(next) => (next ? onOpenChange(true) : requestClose())}
      >
        <DialogContent className="access-ui slim-ui max-w-2xl">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="absolute top-3 right-3 z-10 size-11"
            aria-label="Close invitation"
            disabled={pending}
            onClick={requestClose}
          >
            <X aria-hidden="true" />
          </Button>
          <DialogHeader className="pr-12">
            <DialogTitle>
              {created ? "Send this invitation link" : "Invite a person"}
            </DialogTitle>
          </DialogHeader>
          {created ? (
            <div className="mt-4 flex flex-col gap-5">
              <OneTimeSecret
                label={`Invitation link for ${created.email}`}
                value={created.url}
                copyLabel="Copy link"
              >
                <p>
                  It works once, for 24 hours, and shows only now. Send it to
                  them by any channel.
                </p>
                <p>
                  If it is lost, open them in People and choose Copy a new link.
                </p>
              </OneTimeSecret>
              <DialogFooter className="bg-card sticky -bottom-5 z-10 -mx-5 mt-0 -mb-5 border-t px-5 pt-3 pb-8">
                <Button
                  type="button"
                  className="min-h-11"
                  onClick={requestClose}
                >
                  Done
                </Button>
              </DialogFooter>
            </div>
          ) : (
            <form
              noValidate
              aria-label="Invitation"
              className="mt-4 flex flex-col gap-5"
              onSubmit={submit}
            >
              <div className="grid gap-4 sm:grid-cols-2">
                <TextField
                  id={`${id}-email`}
                  label="Email"
                  type="email"
                  autoComplete="off"
                  required
                  value={form.email}
                  error={errors.email}
                  onChange={(email) => update({ email })}
                />
                <TextField
                  id={`${id}-username`}
                  label="Username"
                  autoComplete="off"
                  required
                  value={username}
                  error={errors.username}
                  onChange={(value) => update({ username: value })}
                />
                <TextField
                  id={`${id}-name`}
                  label="Name"
                  autoComplete="off"
                  maxLength={200}
                  value={form.display_name}
                  onChange={(display_name) => update({ display_name })}
                />
                <TextField
                  id={`${id}-title`}
                  label="Job title"
                  autoComplete="off"
                  maxLength={200}
                  value={form.job_title}
                  onChange={(job_title) => update({ job_title })}
                />
              </div>

              <SelectField
                id={`${id}-role`}
                label="Role"
                value={form.role}
                options={(["member", "guest", "admin"] as const).map(
                  (role) => ({
                    value: role,
                    label: roleLabels[role],
                  }),
                )}
                description={roleDescriptions[form.role]}
                onChange={(value) => {
                  if (
                    value === "member" ||
                    value === "guest" ||
                    value === "admin"
                  )
                    update({ role: value });
                }}
              />

              {form.role === "guest" ? (
                <div className="grid gap-4 sm:grid-cols-2">
                  <SponsorSearchSelect
                    id={`${id}-sponsor`}
                    value={form.sponsor_user_id}
                    error={errors.sponsor}
                    onChange={(sponsor_user_id) => update({ sponsor_user_id })}
                  />
                  <TextField
                    id={`${id}-days`}
                    label="Access length in days"
                    type="number"
                    inputMode="numeric"
                    min={GUEST_DAYS_MIN}
                    max={GUEST_DAYS_MAX}
                    step={1}
                    value={days}
                    description={
                      guestEnds
                        ? `Access ends ${formatDate(guestEnds, region)}.`
                        : settings.isPending
                          ? "Loading the default length…"
                          : `From ${GUEST_DAYS_MIN} to ${GUEST_DAYS_MAX} days.`
                    }
                    error={errors.days}
                    onChange={(value) => update({ days: value })}
                  />
                </div>
              ) : null}

              <FieldSet className="gap-2">
                <FieldLegend className="mb-0">Groups</FieldLegend>
                {form.role === "admin" ? (
                  <p className="text-muted-foreground text-sm">
                    Administrators have full access everywhere, so they are not
                    added to groups.
                  </p>
                ) : groups.length === 0 && !groupSearch.search ? (
                  <p className="text-muted-foreground text-sm">
                    There are no groups yet. Create groups on the Groups tab,
                    then add this person to them.
                  </p>
                ) : (
                  <>
                    <p className="text-muted-foreground text-sm">
                      Access comes from groups.
                      {form.role === "guest" ? " Guests can only read." : ""}
                    </p>
                    <Input
                      type="search"
                      aria-label="Search invitation groups"
                      placeholder="Search groups"
                      className="min-h-11"
                      value={groupSearch.search}
                      onChange={(event) =>
                        groupSearch.onSearchChange(event.target.value)
                      }
                    />
                    <ul className="grid gap-1 rounded-lg border p-2 sm:max-h-56 sm:grid-cols-2 sm:overflow-y-auto">
                      {groups.map((group) => {
                        const checked = form.group_ids.includes(group.id);
                        // The name stays the checkbox's name; what the group
                        // gives is its description (DR-10.1).
                        const nameId = `${id}-group-${group.id}`;
                        const lineId = `${nameId}-gives`;
                        return (
                          <li key={group.id} className="min-w-0">
                            <label className="hover:bg-tint-hover flex min-h-11 cursor-pointer items-start gap-3 rounded-md px-2 py-1.5 text-sm">
                              <Checkbox
                                className="mt-0.5"
                                aria-labelledby={nameId}
                                aria-describedby={lineId}
                                checked={checked}
                                onCheckedChange={(next) =>
                                  update({
                                    group_ids: next
                                      ? [...form.group_ids, group.id]
                                      : form.group_ids.filter(
                                          (item) => item !== group.id,
                                        ),
                                  })
                                }
                              />
                              <span className="min-w-0 flex-1">
                                <span id={nameId} className="block truncate">
                                  {group.name}
                                </span>
                                <span
                                  id={lineId}
                                  className="text-muted-foreground block text-xs break-words"
                                >
                                  {groupAccessLine(
                                    group.access,
                                    form.role,
                                    group.has_other_grants,
                                  )}
                                </span>
                              </span>
                            </label>
                          </li>
                        );
                      })}
                    </ul>
                  </>
                )}
                {groupSearch.loading ? (
                  <p role="status">Loading groups…</p>
                ) : null}
                {groupSearch.error ? (
                  <div role="alert">
                    <p>{groupSearch.error}</p>
                    <Button
                      type="button"
                      variant="outline"
                      className="min-h-11"
                      onClick={() => void groupSearch.retry()}
                    >
                      Retry groups
                    </Button>
                    <ErrorReference id={groupSearch.reference} />
                  </div>
                ) : null}
                {groupSearch.hasMore ? (
                  <Button
                    type="button"
                    variant="outline"
                    className="min-h-11"
                    disabled={groupSearch.loadingMore}
                    onClick={() => void groupSearch.loadMore()}
                  >
                    Load more groups
                  </Button>
                ) : null}
              </FieldSet>

              {settings.isError &&
              form.role === "guest" &&
              form.days === null ? (
                <Alert
                  variant="destructive"
                  reference={apiErrorReference(settings.error)}
                >
                  The default access length could not be loaded. Enter the
                  number of days.
                </Alert>
              ) : null}
              <FieldSet className="gap-2">
                <FieldLegend id={`${id}-delivery`} className="mb-0">
                  How to send
                </FieldLegend>
                {linkOnly ? (
                  <p className="text-muted-foreground text-sm">
                    Email is not set up, so you copy an invitation link and send
                    it to them yourself.
                  </p>
                ) : (
                  <RadioGroup
                    aria-labelledby={`${id}-delivery`}
                    value={delivery}
                    onValueChange={(value) => {
                      if (value === "email" || value === "link")
                        setChosenDelivery(value);
                    }}
                    disabled={pending}
                    className="grid gap-1 sm:grid-cols-2"
                  >
                    {deliveryChoices.map((choice) => (
                      // The line sits outside the label, so the choice's
                      // label is its name alone.
                      <div
                        key={choice.value}
                        className="hover:bg-tint-hover rounded-md px-2 py-1"
                      >
                        <label className="flex min-h-11 cursor-pointer items-center gap-3 xl:min-h-8">
                          <RadioGroupItem
                            value={choice.value}
                            aria-labelledby={`${id}-delivery-${choice.value}`}
                            aria-describedby={`${id}-delivery-${choice.value}-line`}
                          />
                          <span
                            id={`${id}-delivery-${choice.value}`}
                            className="text-sm font-medium"
                          >
                            {choice.label}
                          </span>
                        </label>
                        <p
                          id={`${id}-delivery-${choice.value}-line`}
                          className="text-muted-foreground pb-1 pl-7 text-xs"
                        >
                          {choice.line}
                        </p>
                      </div>
                    ))}
                  </RadioGroup>
                )}
              </FieldSet>

              <ActionError
                message={submitError}
                reference={submitErrorFailure?.reference}
              />

              <DialogFooter className="bg-card sticky -bottom-5 z-10 -mx-5 mt-0 -mb-5 border-t px-5 pt-3 pb-8">
                <Button
                  type="button"
                  variant="ghost"
                  className="min-h-11"
                  disabled={pending}
                  onClick={requestClose}
                >
                  Cancel
                </Button>
                <DisabledReason reason={verifying ? verifyingReason : null}>
                  <Button
                    type="submit"
                    className="min-h-11"
                    pending={pending}
                    pendingLabel={
                      delivery === "link" ? "Creating…" : "Sending…"
                    }
                  >
                    {delivery === "link" ? (
                      <Link2 aria-hidden="true" />
                    ) : (
                      <Send aria-hidden="true" />
                    )}
                    {delivery === "link"
                      ? "Create invitation link"
                      : "Send invitation"}
                  </Button>
                </DisabledReason>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>
      <DiscardChangesDialog
        open={confirmDiscard}
        title="Discard this invitation?"
        description="The details you entered will be lost."
        error={discardError}
        onKeep={() => setConfirmDiscard(false)}
        onDiscard={() => {
          if (!discard())
            setDiscardError(
              "Your draft could not be cleared from this browser. Keep editing, or try again.",
            );
        }}
      />
    </>
  );
}
