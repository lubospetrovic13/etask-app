# Application request: Onboarding a new employee

> This is a request from the business, not a technical design. It is written
> the way the process is described in a meeting. How it gets built is the
> platform's problem.

## Why we want it

When somebody new joins us, they need accounts in three systems: **Entra ID**,
**Atlassian** and the **Netgrif portal**. Today this runs on e-mail. Nobody can
say what state it is in, who has already done their part and who has not, and
it happens that a person turns up on Monday with nothing to log in to.

We want one request, one approval, and a place where you can see where it is
stuck.

## How it should work

1. **HR raises an onboarding request.** They fill in the first and last name,
   work e-mail, position, cost centre and start date. They also **pick the
   manager** who is to approve this onboarding.

2. **The chosen manager approves the request or sends it back** for completion.
   When sending it back, they write why, so HR knows what to add. A returned
   request can be edited and submitted again.

3. **After approval the accounts get created.** The IT administrator ticks off
   what is done: Entra ID, Atlassian, Netgrif portal. They can see the details
   from the request while doing it, so they do not have to look anywhere else.

4. **Once all three are done, the onboarding is complete.** HR and the manager
   both see it on their own list without having to ask anyone.

## What has to be visible in the portal

| who | what they need to see |
|---|---|
| HR | my requests and what state they are in |
| manager | what is waiting for my approval |
| IT administrator | whose accounts I need to create |
| everyone involved | completed onboardings |

The list should show the new joiner's name, the start date, the state and who
is approving.

## The rules that matter

* **Only that one chosen manager approves**, not anyone who happens to hold
  the role.
* **Nothing gets created before approval.** Not a single account.
* **The requester must not approve their own request.**
* A returned request is not thrown away; the same one carries on.

## What we are not solving yet

The real integration with Entra ID and Atlassian. For now it is enough that
the IT administrator ticks the accounts off by hand. The integration comes
later and the process must not have to change for it, only who does the
ticking off.

## How we will try it out

On a test account we will walk the whole path: raise a request, have it sent
back, complete it, approve it, tick off the three accounts and see that the
onboarding is complete. We want to know that it can be walked through like
this, not merely that it can be clicked together.
