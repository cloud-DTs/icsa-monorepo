ACTION_DEPLOY = "DEPLOY"
ACTION_DESTROY = "DESTROY"
ACTION_NO_CHANGE = "NO_CHANGE"
ACTION_UPDATE = "UPDATE"

ACTIONABLE_ACTIONS = (ACTION_DESTROY, ACTION_DEPLOY, ACTION_UPDATE)


def pending_actions(actions, action_name):
  # In-place updates use the same forward dependency order as creation.
  phase_actions = (ACTION_DEPLOY, ACTION_UPDATE) if action_name == ACTION_DEPLOY else (action_name,)
  return [
    action for action in actions
    if action["action"] in phase_actions
    and not action.get("processed", False)
    and not action.get("blocked", False)
  ]


def deploy_groups(plan):
  return plan


def destroy_groups(plan):
  return reversed(plan)
