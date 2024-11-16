#!/usr/bin/env python

from __future__ import annotations

from ansible.plugins.action import ActionBase
from ansible.utils.display import Display
from ansible.playbook.play import Play
from ansible.executor.task_queue_manager import TaskQueueManager
from ansible.inventory.manager import InventoryManager

display = Display()

class ActionModule(ActionBase):

    args = None
    call_args = None

    def run(self, tmp=None, task_vars=None):
        ''' Wrap Ansible's include_role '''
        if task_vars is None:
            task_vars = dict()

        old_local = task_vars.get('local', {})

        args = self._task.args
        self.args = args
        call_args = old_local.get('call_args', {})
        self.call_args = call_args
        role_name = self.get_include_role_arg('name')
        allow_duplicates = self.get_include_role_arg('allow_duplicates')
        public = self.get_include_role_arg('public')
        rolespec_validate = self.get_include_role_arg('rolespec_validate')
        args.update({
            'name': role_name or (task_vars.get('ansible_role_name', None)),
            'allow_duplicates': allow_duplicates if allow_duplicates is not None else True,
            'defaults_from': self.get_include_role_arg('defaults_from') or 'main',
            'handlers_from': self.get_include_role_arg('handlers_from') or 'main',
            'public': public if public is not None else True,
            'rolespec_validate': rolespec_validate if rolespec_validate is not None else True,
            'tasks_from': self.get_include_role_arg('tasks_from') or ('tasks' if role_name is None else 'main'),
            'vars_from': self.get_include_role_arg('vars_from') or 'main',
        })

        extra_task_vars = {}

        # set deprecated task vars
        if (
            task_vars.get('ansible_role_name', None) == 'pieterjanv.localscope.call' and
            isinstance(task_vars.get('target', {}), dict)
        ):
            for key in ['target', 'input']:
                v = self._templar.template(task_vars.get('target', {})).get(key, None)
                if v is not None:
                    extra_task_vars[key] = v
                elif key in task_vars:
                    del task_vars[key]

        input = args.get('input', self._templar.template(task_vars.get('input',
            old_local.get('input', None)
        ) if role_name is None else None))
        if 'input' in args:
            del args['input']
        if input is not None:
            extra_task_vars.update(input)

        pieterjanv_localscope_stack = task_vars.get('pieterjanv_localscope_stack', [])
        private_locals = old_local.get('_', {})
        new_local = (
            {
                **({ 'input': input } if input is not None else {}),
                **{
                    'callee': args.get('name'),
                    '_': {
                        **self.get_deprecated_target_arg(
                            'target',
                            task_vars,
                            private_locals,
                        ),
                        **self.get_deprecated_target_arg(
                            'call_args',
                            task_vars,
                            private_locals,
                        ),
                        **self.get_deprecated_target_arg(
                            'input',
                            task_vars,
                            private_locals,
                        ),
                    }
                },
            }
        )

        play = Play.load(
            {
                'hosts': task_vars['inventory_hostname'],
                'gather_facts': 'no',
                'tasks': [
                    {
                        'name': 'push to stack',
                        'ansible.builtin.set_fact': {
                            'pieterjanv_localscope_stack': (
                                pieterjanv_localscope_stack +
                                [old_local]
                            )
                        },
                    },
                    {
                        'name': 'initialize local',
                        'ansible.builtin.set_fact': {
                            'local': new_local
                        },
                    },
                    {
                        'name': 'include role',
                        'ansible.builtin.include_role': args,
                        'vars': extra_task_vars,
                    },
                    {
                        'name': 'restore local',
                        'ansible.builtin.set_fact': {
                            'local': "{{ pieterjanv_localscope_stack[-1] }}"
                        },
                    },
                    {
                        'name': 'pop from stack',
                        'ansible.builtin.set_fact': {
                            'pieterjanv_localscope_stack': "{{ pieterjanv_localscope_stack[:-1] }}"
                        },
                    },
                ]
            },
            variable_manager=self._task._parent._variable_manager,
            loader=self._task._parent._loader,
            vars=task_vars,
        )

        inventory = InventoryManager(self._task._parent._loader)
        inventory.add_host(task_vars['inventory_hostname'])
        result = {'changed': False}

        tqm = None
        try:
            tqm = TaskQueueManager(
                inventory=inventory,
                variable_manager=self._task._parent._variable_manager,
                loader=self._task._parent._loader,
                passwords={
                    'conn_pass': self._play_context.password,
                    'become_pass': self._play_context.become_pass,
                }
            )
            tqm.run(play)
        except Exception as e:
            display.error(f"Error running TaskQueueManager: {e}")
            result = {'failed': True, 'msg': str(e)}
        finally:
            if tqm:
                tqm.cleanup()


        final_result = super(ActionModule, self).run(tmp, task_vars)
        final_result.update(result)
        return final_result
    
    def get_include_role_arg(self, name):
        return self.args.get(
            name,
            self.args.get('target', {}).get(
                name,
                self.call_args.get(name)
            )
        )
    
    def get_deprecated_target_arg(self, name, task_vars, private_locals):
        target = self._templar.template(task_vars.get('target', None))
        if not target or not isinstance(target, dict):
            return {}
        value = target.get(name, private_locals.get(name, None))
        if value is None:
            return {}
        return { name: value }

