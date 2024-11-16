# pieterjanv.localscope - Ansible collection that makes roles behave more like functions


An Ansible collection that provides roles with localscope, eager evaluation of
arguments, and return values.

- **locally scoped facts**; facts that are only 
visible to the role that set them. This aims to solve the problem of global 
scope in Ansible roles, where intermediate results can be overwritten by 
included roles.
- **arguments that are evaluated eagerly**; This prevents arguments from 
evaluating to unintended  values when some nested variable name conflicts.
- **return values**; `register` a name to capture the return value of a role.

And it should allow this without changing the way roles are are consumed, i.e. 
without requiring the consumer to use the plugin directly.


## Table of contents

- [Installation](#installation)
  - [From GitHub](#from-github)
  - [Locally](#locally)
- [Usage](#usage)
- [Background](#background)
  - [Motivation](#motivation)
  - [Proof of concept solution](#proof-of-concept-solution)
    - [Example of the solution](#example-of-the-solution)
  - [On backwards compatibility](#on-backwards-compatibility)
  - [Pitfalls](#pitfalls)


## Installation

At the moment the collection is not available on Ansible Galaxy, so it must be
installed either from GitHub or locally.


### From GitHub

1. Add the following to your `requirements.yml`:

```yaml
collections:
  - source: https://github.com/pieterjanv/ansible-local-facts
    type: git
    version: main # or a specific tag
```

2. Run the following command (to force an update, append the `--force` flag):

```bash
ansible-galaxy collection install -r requirements.yml
```


### Locally

1. Clone the repository:

```bash
git clone https://github.com/pieterjanv/ansible-local-facts.git
```

2. Install the collection (to force an update, append the `--force` flag):

```bash
cd ansible-local-facts
ansible-galaxy collection install .
```


## Usage

This collection contains a plugin called `pieterjanv.localscope.include_role` 
that wraps `ansible.builtin.include_role`. The plugin can be used to call 
arbitrary roles, providing them with a fact called `local` 
that is only visible to the role being called. Furthermore, the plugin ensures
that any role arguments passed under the `input` key are evaluated eagerly,
and made available at both `local.input` and as regular variables.

Secondly, an action plugin called `pieterjanv.localscope.set` is provided, 
that allows a straightforward way of setting the `local` fact.

Finally, an action plugin called `pieterjanv.localscope.return` is provided,
that allows a role to return a value at the `register`ed key.

Instead of calling the `pieterjanv.localscope.include_role`
directly, it is recommended to use a small amount of boilerplate in
`tasks/main.yml` of the roles that should have locally scoped facts, because 
this allows the roles to be called as usual.

The boilerplate is as follows:

```yaml
--- # Path: roles/my_role/tasks/main.yml

# Include the role using the custom `include_role` plugin to provide this role 
# with a locally scoped `local` fact.
# Optionally, specify the file in the tasks folder that contains the tasks, as
# well as any other `include_role` parameters.
# By default, `include_role` will include `tasks/tasks` if included without
# a `name` argument, and `tasks/main` if called with a `name` argument.
# This default allows one to omit the `tasks_from` parameter while preventing
# the infinite loop that would result if `tasks/main.yml` were included in the
# case of leaving the `name` parameter unspecified.
- ansible.builtin.include_role:
    name: pieterjanv.localscope.call
  register: my_output # when returning a value

# When returning a value, make sure to use the `pieterjanv.localscope.return`
# plugin to set the value to the `register`ed key set by the consumer.
- pieterjanv.localscope.return: "{{ my_output }}"
```

Then, in the role's `tasks/tasks.yml` file, the `local` fact can be used as follows:

```yaml
--- # Path: roles/my_role/tasks/tasks.yml

- name: Any values passed to this role under `input` are available at `local.input`
  ansible.builtin.debug:
    var: local.input.my_parameter

- name: Set some locally scoped facts
  pieterjanv.localscope.set:
    updates:
      some_key: some value
      another:
        key: another value

- name: Add one more value with recursive merging
  pieterjanv.localscope.set:
    updates:
      another:
        key2: yet another value
    recursive: yes

# When calling a role that may or may not use locally scoped facts, we have
# to wrap it with `pieterjanv.localscope.include_role` to ensure that our facts 
# cannot be overwritten by the called role.
# To wrap a role, set the `include_role` parameters as usual, and include the
# role arguments under the `input` parameter.
# The values under the `input` parameter are set on `local.input` in the called 
# role, as well as being available as regular variables.
- name: Include a nested role
  pieterjanv.localscope.include_role:
    name: some_one.some_collection.some_role
    input:
      some_local_var: some value
      eagerly_evaluated: "{{ local.some_key }}"
  # will default to a dictionary with only the `changed` and `failed` keys
  register: nested_output

- name: Use the locally scoped facts knowing they have not been overwritten
  debug:
    msg: "{{ [
      local.input.some_parameter,
      local.some_key,
      local.another.key,
      local.another.key2,
    ] }}"

# Optionally, return a value to the consumer. The return value must be a
# dictionary, and will be set to the key as `register`ed by the consumer.
# Note that Ansible always sets the `changed` and `failed` keys on the
# registered variable.
- name: Return a value
  pieterjanv.localscope.return:
    my_return_value: "some value"
```


## Background

In the `example` directory you can find three sets of roles:

1. `naive_outer` and `naive_nested`, which demonstrate the problem of global scope. See [Motivation](#motivation).
2. `call`, `locally_scoped_outer` and `locally_scoped_nested`, which demonstrate the proposed solution in its simplest and clearest form. See
[Proof of concept solution](#proof-of-concept-solution).
3. `robust_call`, `robust_locally_scoped_outer` and 
`robust_locally_scoped_nested`, which demonstrate a more robust version of the 
solution. See [On backwards compatibility](#on-backwards-compatibility).

Run the following commands to see the example in action:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip3 install -r requirements.txt
ansible-playbook example/main.yml
```


### Motivation

During configuration it is often useful to calculate values and store them as
intermediate results; for efficiency, readability, or to avoid repetition. In
Ansible, this can be done using `set_fact` or `register`, but the resulting
variables are written to the host vars for the current host which can be 
overwritten by included roles. This can lead to unexpected behavior and bugs, 
especially in larger playbooks or roles.

One strategy to avoid this is to prefix every role-specific variable with
the role name. This can be cumbersome and error-prone.

Alternatively, we can try to limit the scope of intermediate variables to the
role that created them.


#### Example of the problem

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

The problem is that the `my_intermediate_result` fact is global and is overwritten by the nested role.


### Proof of concept solution

The proposal in this repository is to call the role with a wrapper role around `include_role` called `call` that 
maintains a stack of dictionaries. Each time the wrapper is included it completes the following steps:

1. Push the current value of the `local` fact, defaulting to an empty dictionary
in the case of the first usage of `call`
2. Initialize the `local` fact for the called role to the `input` variable if defined, empty otherwise.
3. Include the role.
4. Restore the `local` fact to the top of the stack.
5. Pop the stack.

The result is that the `local` fact can be used by the role to store intermediate results without the risk of it being overwritten by other roles.


#### Example of the solution

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
        name: roles/locally_scoped_outer


--- # Path: roles/call/tasks/main.yml

- name: push to stack
  ansible.builtin.set_fact:
    my_stack: "{{ my_stack | default([]) + [local | default({})] }}"

- name: initialize local
  ansible.builtin.set_fact:
    local: "{{ input | default({}) }}"

- ansible.builtin.include_role:
    name: "{{ name }}"

- name: restore local
  ansible.builtin.set_fact:
    local: "{{ my_stack[-1] }}"

- name: pop from stack
  ansible.builtin.set_fact:
    my_stack: "{{ my_stack[:-1] }}"


--- # Path: roles/locally_scoped_outer/tasks/main.yml

- name: set a fact under a generic name
  ansible.builtin.set_fact:
    local: "{{ local | combine({
      'my_intermediate_result': 'outer',
    }) }}"

- name: include a nested role
  ansible.builtin.include_role:
    name: roles/call
  vars:
    name: roles/locally_scoped_nested

- name: assert the fact is what we want
  ansible.builtin.assert:
    that:
      - local.my_intermediate_result == "outer"


--- # Path: roles/locally_scoped_nested/tasks/main.yml

- name: set a fact under a generic name
  ansible.builtin.set_fact:
    local: "{{ local | combine({
      'my_intermediate_result': 'nested',
    }) }}"
```

The assertion succeeds.


### On backwards compatibility

For backwards compatibility and ease of use it is desirable to keep the way roles are consumed unchanged. This is 
demonstrated by the roles `robust_locally_scoped_outer` and 
`robust_locally_scoped_nested`, which can be called without explicitly 
utilizing the `call` role; `include_role`, `import_role` and the `roles`
keyword can be used directly.

This comes at the cost of having to include a tiny bit of boilerplate in
`tasks/main.yml` of these roles, and moving the actual tasks to a separate file.


### Pitfalls

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
            name: roles/locally_scoped_outer
      when: local.my_intermediate_result is not defined
```

This will not fail, but will skip about half of the tasks, rather than all or none of them. This is because the `local.my_intermediate_result` fact
becomes defined about midway through the `call` role, and since `when` on a
block applies the condition seperately to all tasks under it and `include_role` 
simply inserts the tasks at the point of inclusion, the `when` condition 
becomes false about halfway through.

In this case a workaround would be to factor out the block's tasks into a separate role and apply the `when` condition to `include_role`.
