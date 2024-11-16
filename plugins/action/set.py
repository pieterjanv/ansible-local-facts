#!/usr/bin/env python

from __future__ import annotations

# from ansible.config.manager import ensure_type
from ansible.errors import AnsibleError, AnsibleFileNotFound, AnsibleAction, AnsibleActionFail
# from ansible.module_utils.six import string_types
from ansible.plugins.action import ActionBase
# from ansible.plugins.loader import lookup_loader
from ansible.utils.display import Display
# from ansible.plugins.action import set_fact

display = Display()

class ActionModule(ActionBase):

    def run(self, tmp=None, task_vars=None):
        ''' Add facts to the some fact '''
        if task_vars is None:
            task_vars = dict()

        updates = self._task.args.get('updates', None)
        if (updates is None) or (not isinstance(updates, dict)):
            raise AnsibleError('Updates must be a dictionary')
        
        recursive = self._task.args.get('recursive', False)

        self._task._register = self._task._register or 'local'

        return {
            **self._update_local(task_vars, updates, recursive),
            'changed': False,
        }
    
    def _update_local(self, task_vars, updates, recursive):
        ''' Apply updates '''
        hostvars = task_vars.get('hostvars', {}).get(task_vars.get('inventory_hostname', None), None)
        if hostvars is None:
            raise Exception('hostvars not found')
        return self._update(hostvars.get(self._task._register, {}), updates, recursive)

    def _update(self, target, updates, recursive):
        ''' Apply updates to the target '''
        for key, value in updates.items():
            templated_key = self._templar.template(key)
            if recursive and isinstance(value, dict):
                target[templated_key] = self._update(target.get(key, {}), value, recursive)
            else:
                target[templated_key] = self._templar.template(value)
        return target
