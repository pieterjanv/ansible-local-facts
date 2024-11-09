# Allow Ansible roles to scope facts locally


This repository contains a simple proposal for providing Ansible roles with locally scoped variables.

Because the proposal has not been extensively tested, it is meant to invite discussion and feedback.

Run the following commands to see the example in action:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip3 install -r requirements.txt
ansible-playbook src/main.yml
```


## Motivation

During configuration it is often useful to calculate values and store them as
intermediate results; for efficiency, readability, or to avoid repetition. In
Ansible, this can be done using `set_fact` or `register`, but the resulting
variables are written to the host vars for the current host which can be 
overwritten by included roles. This can lead to unexpected behavior and bugs, 
especially in larger playbooks or roles.

One strategy to avoid this is to prefix every role-specific variable with
the role name. This can be cumbersome and error-prone, especially when
variables are passed between roles.

Alternatively, we can try to limit the scope of intermediate variables to the
role that created them.


### Example of the problem

Consider the setup of including a role that calculates a value and stores it,
then including some role that happens to set the same fact before finishing
up:

```yaml
--- # Path: main.yml

- name: Demonstrate a problem with global scope
  hosts: localhost
  gather_facts: false
  roles:
    - role: naive_outer


--- # Path: roles/naive_outer/tasks/main.yml

- name: set a fact under a generic name
  ansible.builtin.set_fact:
    my_intermediate_result: "outer"

- name: include a nested role
  ansible.builtin.include_role:
    name: naive_nested

- name: assert the fact is what we want
  ansible.builtin.assert:
    that:
      - my_intermediate_result == "outer"


--- # Path: roles/naive_nested/tasks/main.yml

- name: set a fact under a generic name
  ansible.builtin.set_fact:
    my_intermediate_result: "nested"
```

The above playbook will fail with the following error:

```
fatal: [localhost]: FAILED! => {
    "assertion": "my_intermediate_result == \"outer\"",
    "changed": false,
    "evaluated_to": false,
    "msg": "Assertion failed"
}
```

which is likely not what we intended. The problem is that the `my_intermediate_result` fact is global and is overwritten by the nested role.


## Proof of concept solution

The proposal in this repository is to call the role with a wrapper role around `include_role` called `call` that maintains a stack of dictionaries. Each time
the wrapper is included it does the following five steps:

1. Replace the top of the stack with the current value of the `local` fact, if 
it exists, then push a new role context onto the stack. The new context equals 
the `input` fact if defined, defaulting to an empty dictionary.
2. Set the `local` fact to the top of the stack.
3. Include the role.
4. Pop the context from the stack.
5. Reset the `local` fact to the top of the stack.

The result is that the `local` fact can be used by the role to store intermediate results without the risk of it being overwritten by other roles.


### Example of the solution

The following playbook demonstrates the use of the `call` role:

```yaml
--- # Path: main.yml

- name: Demonstrate use of local scope
  hosts: localhost
  gather_facts: false
  tasks:

    - ansible.builtin.include_role:
        name: roles/call
      vars:
        role: roles/locally_scoped_outer


--- # Path: roles/call/tasks/main.yml

- name: push to stack
  set_fact:
    my_stack: "{{ (
      my_stack[:-1] + [local] if my_stack is defined and my_stack | length > 0
      else []
    ) + [input | default({})] }}"

- name: update local
  ansible.builtin.set_fact:
    local: "{{ my_stack[-1] }}"

- ansible.builtin.include_role:
    name: "{{ role }}"

- name: pop from stack
  set_fact:
    my_stack: "{{ my_stack[:-1] }}"

- name: update local
  ansible.builtin.set_fact:
    local: "{{
      my_stack[-1] if my_stack is defined and my_stack | length > 0
      else None
    }}"


--- # Path: roles/locally_scoped_outer/tasks/main.yml

- name: set a fact under a generic name
  ansible.utils.update_fact:
    updates:
      - path: my_intermediate_result
        value: "outer"
  register: local

- name: include a nested role
  ansible.builtin.include_role:
    name: roles/call
  vars:
    role: roles/locally_scoped_nested

- name: assert the fact is what we want
  ansible.builtin.assert:
    that:
      - local.my_intermediate_result == "outer"


--- # Path: roles/locally_scoped_nested/tasks/main.yml

- name: set a fact under a generic name
  ansible.utils.update_fact:
    updates:
      - path: my_intermediate_result
        value: nested
  register: local
```

The assertion succeeds.


## Pitfalls

Because the `local` fact is host-wide, there are still problems that can arise.

I've already run into the following:

```yaml
--- # Path: main.yml

- name: Demonstrate a pitfall despite local scope
  hosts: localhost
  gather_facts: false
  tasks:

    - block:
        - ansible.builtin.include_role:
            name: roles/call
          vars:
            role: roles/locally_scoped_outer
      when: local.my_intermediate_result is not defined
```

This will not fail, but will skip about half of the tasks, rather than all or none of them. This is because the `local.my_intermediate_result` fact
becomes defined about midway through the `call` role, and since `when` on a
block applies the condition seperately to all tasks under it and `include_role` 
simply inserts the tasks at the point of inclusion, the `when` condition 
becomes false about halfway through.

In this case a workaround would be to factor out the block's tasks into a separate role and apply the `when` condition to `include_role`.
