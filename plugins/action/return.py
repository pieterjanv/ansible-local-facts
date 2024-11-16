#!/usr/bin/env python

from __future__ import annotations

from ansible.errors import AnsibleError, AnsibleFileNotFound, AnsibleAction, AnsibleActionFail
from ansible.plugins.action import ActionBase
from ansible.plugins.loader import action_loader
from ansible.utils.display import Display

display = Display()

class ActionModule(ActionBase):

    def run(self, tmp=None, task_vars=None):
        ''' Set a return value to a fact reserved for output '''
        if task_vars is None:
            task_vars = dict()

        output_name = 'pieterjanv_localscope_output'

        set_task = self._task.copy()
        set_task.args.clear()
        set_task._register = output_name
        set_task.args.update({
            'updates': self._task.args,
        })
        set_plugin = action_loader.get(
            'pieterjanv.localscope.set',
            set_task,
            connection=self._connection,
            play_context=self._play_context,
            loader=self._loader,
            templar=self._templar,
            shared_loader_obj=self._shared_loader_obj,
        )

        self._task._register = output_name
        return set_plugin.run(tmp, task_vars)
