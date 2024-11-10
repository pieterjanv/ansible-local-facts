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

    changed = False

    def run(self, tmp=None, task_vars=None):
        ''' Add facts to the `local` fact '''
        if task_vars is None:
            task_vars = dict()

        updates = self._task.args.get('updates', None)
        if (updates is None) or (not isinstance(updates, dict)):
            raise AnsibleError('Updates must be a dictionary')
        
        recursive = self._task.args.get('recursive', False)

        self._task._register = 'local'

        return {
            **self._update_local(task_vars, updates, recursive),
            'changed': False,
        }
    
    def _update_local(self, task_vars, updates, recursive):
        ''' Apply updates to the `local` fact '''
        hostvars = task_vars.get('hostvars', {}).get(task_vars.get('inventory_hostname', None), None)
        if hostvars is None:
            raise Exception('hostvars not found')
        return self._update(hostvars.get('local', {}), updates, recursive)

    def _update(self, target, updates, recursive):
        ''' Apply updates to the target '''
        for key, value in updates.items():
            templated_key = self._templar.template(key)
            if recursive and isinstance(value, dict):
                target[templated_key] = self._update(target.get(key, {}), value, recursive)
            else:
                display.vvvv('Setting %s to %s' % (templated_key, value))
                target[templated_key] = self._templar.template(value)
        return target
    
    def isEqual(self, a, b):
        ''' Compare two values '''
        if isinstance(a, dict) and isinstance(b, dict):
            return self._compareDict(a, b)
        elif isinstance(a, list) and isinstance(b, list):
            return self._compareList(a, b)
        else:
            return a == b
        
    def _compareDict(self, a, b):
        ''' Compare two dictionaries '''
        if len(a) != len(b):
            return False
        for key, value in a.items():
            if not self.isEqual(value, b.get(key, None)):
                return False
        return True
    
    def _compareList(self, a, b):
        ''' Compare two lists '''
        if len(a) != len(b):
            return False
        for i in range(len(a)):
            if not self.isEqual(a[i], b[i]):
                return False
        return True
