# Zero Touch Grading Implementation Session Log

**Date**: 2026-04-01  
**Lab**: Build Secure Streamlined Developer Workflows with RHADS  
**Showroom Repo**: https://github.com/rhpds/unified-devsecops-delivery-showroom  
**Scripts Repo**: https://github.com/rhpds/rhpds.build-secured-dev-workflows

---

## Objective

Add Zero Touch (ZT) grading to an existing Showroom lab with 4 modules, using pre-existing solve/validate bash scripts deployed on a bastion VM.

---

## Lab Architecture

**Critical Understanding** (took several iterations to clarify):

```
┌─────────────────────────────────────────────────────────────┐
│ OpenShift Cluster                                            │
│                                                              │
│  ┌──────────────────┐         ┌──────────────────┐          │
│  │ Showroom UI Pod  │────────▶│ zt-runner Pod    │          │
│  │ (Antora + UI)    │         │ (ansible-runner) │          │
│  └──────────────────┘         └─────────┬────────┘          │
│                                          │                   │
│                                          │ SSH               │
└──────────────────────────────────────────┼───────────────────┘
                                           │
                                           ▼
                              ┌────────────────────────┐
                              │ Bastion VM             │
                              │                        │
                              │ $HOME/lab-assets/      │
                              │ ├── solve-module-1.sh  │
                              │ ├── solve-module-2.sh  │
                              │ ├── validate-module-*.sh│
                              │ └── helper scripts...  │
                              └────────────────────────┘
```

**Key Points**:
- Showroom UI runs in OpenShift pod (not on bastion)
- zt-runner runs in OpenShift pod (not on bastion)
- Scripts are deployed on bastion VM by AgV workload
- zt-runner must SSH to bastion to execute scripts

---

## Initial Confusion & Resolution

### Misconception 1: Architecture Type
**Initial assumption**: "Showroom on OpenShift" meant OCP tenant lab (zt-runner in pod with direct cluster access)  
**Reality**: OCP + Bastion VM hybrid (zt-runner in pod, must SSH to bastion)  
**Resolution**: User clarified by sharing reference: https://github.com/rhpds/ocp-zt-dedicated-showroom/blob/main/runtime-automation/module-02/solve.yml

### Misconception 2: Script Location
**Initial assumption**: Inline all script content into playbooks  
**Reality**: Scripts already exist on bastion at `$HOME/lab-assets/`, deployed by AgV workload  
**Resolution**: Playbooks should call existing scripts, not recreate them

### Misconception 3: Inventory Management
**Initial assumption**: Need static inventory file  
**Reality**: Use dynamic inventory with `add_host` pattern  
**Resolution**: Build SSH inventory in first play, use it in second play

---

## Implementation Approach

### What We Did NOT Do (User Corrections)

❌ **Inline all bash logic into playbooks** — Too complex, defeats purpose of existing scripts  
❌ **Copy scripts from source repo to showroom repo** — Scripts deployed by AgV, not showroom  
❌ **Use `ansible.builtin.script` to copy from showroom** — Reference example does this, but not needed here  
❌ **Create static inventory file** — Dynamic inventory via `add_host` is cleaner  
❌ **Use `hosts: localhost`** — Would run in zt-runner pod, not on bastion

### What We DID (Final Solution)

✅ **Created scaffold** — Updated `site.yml` (nookbag v0.0.3) + `ui-config.yml` (zero-touch type)  
✅ **Simple playbook pattern** — Two plays: (1) build SSH inventory, (2) run script on bastion  
✅ **Minimal implementation** — Just call existing scripts, no recreation  
✅ **setup.yml stubs** — Placeholder for potential future use  
✅ **All 4 modules** — Consistent pattern across modules 1-4

---

## Final Playbook Pattern

### solve.yml (all modules)
```yaml
---
# Module X — run existing solve-module-X.sh on bastion
- name: Build SSH inventory
  hosts: localhost
  gather_facts: false
  tasks:
    - ansible.builtin.add_host:
        name: bastion
        ansible_host: "{{ bastion_host }}"
        ansible_port: "{{ bastion_port | default(22) }}"
        ansible_user: "{{ student_user }}"
        ansible_password: "{{ bastion_password }}"
        ansible_ssh_common_args: "-o StrictHostKeyChecking=no"

- name: Module X Solve — run solve-module-X.sh on bastion
  hosts: bastion
  gather_facts: false
  tasks:
    - name: Run solve-module-X.sh
      ansible.builtin.shell: |
        bash $HOME/lab-assets/solve-module-X.sh
      register: r_solve

    - name: Show output
      ansible.builtin.debug:
        msg: "{{ r_solve.stdout }}"
```

### validation.yml (all modules)
```yaml
---
# Module X — run existing validate-module-X.sh on bastion
- name: Build SSH inventory
  hosts: localhost
  gather_facts: false
  tasks:
    - ansible.builtin.add_host:
        name: bastion
        ansible_host: "{{ bastion_host }}"
        ansible_port: "{{ bastion_port | default(22) }}"
        ansible_user: "{{ student_user }}"
        ansible_password: "{{ bastion_password }}"
        ansible_ssh_common_args: "-o StrictHostKeyChecking=no"

- name: Module X Validation — run validate-module-X.sh on bastion
  hosts: bastion
  gather_facts: false
  tasks:
    - name: Run validate-module-X.sh
      ansible.builtin.shell: |
        bash $HOME/lab-assets/validate-module-X.sh
      register: r_validate
      ignore_errors: true

    - name: Show output
      ansible.builtin.debug:
        msg: "{{ r_validate.stdout }}"

    - name: Fail if validation failed
      ansible.builtin.fail:
        msg: "Module X validation failed"
      when: r_validate.rc != 0
```

---

## File Structure Created

```
unified-devsecops-delivery-showroom/
├── site.yml                          # Updated: nookbag v0.0.3
├── ui-config.yml                     # Updated: type=zero-touch, module config
└── runtime-automation/
    ├── module-01/
    │   ├── setup.yml                 # Stub placeholder
    │   ├── solve.yml                 # Calls solve-module-1.sh on bastion
    │   └── validation.yml            # Calls validate-module-1.sh on bastion
    ├── module-02/
    │   ├── setup.yml
    │   ├── solve.yml
    │   └── validation.yml
    ├── module-03/
    │   ├── setup.yml
    │   ├── solve.yml
    │   └── validation.yml
    └── module-04/
        ├── setup.yml
        ├── solve.yml
        └── validation.yml
```

---

## Prerequisites (AgV Side)

For this implementation to work, the **AgnosticV catalog** must:

### 1. Deploy Scripts to Bastion
The bastion VM must have these scripts at `$HOME/lab-assets/`:
- `solve-module-1.sh` through `solve-module-4.sh`
- `validate-module-1.sh` through `validate-module-4.sh`
- Helper scripts called by solve scripts:
  - Module 1: `reset-module-1.sh`, `install-rhtpa.sh`, `upload-sbom.sh`
  - Module 2: `reset-module-2.sh`, `install-rhtas.sh`, `test-image-signing.sh`
  - Module 3: `reset-module-3.sh`, helper scripts for user/config creation
  - Module 4: `reset-module-4.sh`, `configure-acs.sh`, `test-image-scanning.sh`
- YAML manifest templates (referenced by install scripts)
- Example files (e.g., `example-sbom.json`)

**Source**: These live in https://github.com/rhpds/rhpds.build-secured-dev-workflows under `roles/lab_scripts/templates/`

### 2. Pass Environment Variables to zt-runner
The zt-runner pod must receive these variables (typically via AgV userdata):

**Required**:
- `bastion_host` — Bastion VM hostname/IP
- `student_user` — SSH username for bastion
- `bastion_password` — SSH password for bastion

**Optional**:
- `bastion_port` — SSH port (defaults to 22)

**Additional vars for scripts**:
- `CLUSTER_DOMAIN` — OpenShift cluster ingress domain
- `GUID` — Lab GUID

### 3. Example AgV Workload Configuration
```yaml
# In your AgV catalog common.yaml
workloads:
  - rhpds.ftl.ocp4_workload_runtime_automation_k8s  # For OCP tenant
  # OR
  - rhpds.ftl.vm_workload_runtime_automation         # For RHEL VM

# Showroom configuration
ocp4_workload_showroom_deployer_chart_name: zerotouch
ocp4_workload_showroom_deployer_chart_version: "1.9.18"
ocp4_workload_showroom_runtime_automation_image: "quay.io/rhpds/zt-runner:v2.3.0"
ocp4_workload_showroom_zero_touch_ui_enabled: true

# Userdata passed to zt-runner
agnosticd_user_data:
  bastion_host: "{{ bastion_public_hostname }}"
  student_user: "{{ student_name }}"
  bastion_password: "{{ student_password }}"
  CLUSTER_DOMAIN: "{{ openshift_cluster_ingress_domain }}"
  GUID: "{{ guid }}"
```

---

## Key Learnings for Claude-Skilled Developers

### 1. **Clarify Architecture Early**
When implementing ZT grading, first question to ask:
- "Where does the zt-runner execute?" (pod vs bastion)
- "Where are the scripts located?" (deployed by AgV vs copied from showroom)
- "Does this lab have a bastion VM?"

Don't assume — ask explicitly or request reference examples.

### 2. **Follow User's Existing Patterns**
User had scripts at `/Users/treddy/gpte/github/rhpds/rhpds.build-secured-dev-workflows/roles/lab_scripts/templates/`

**Wrong approach**: "Let me inline all this into Ansible"  
**Right approach**: "How do you want these called?" → User: "Just run them on bastion where they're already deployed"

### 3. **Reference Examples Are Gold**
When user shared https://github.com/rhpds/ocp-zt-dedicated-showroom/blob/main/runtime-automation/module-02/solve.yml, it immediately clarified:
- `add_host` pattern for dynamic inventory
- `ansible.builtin.script` vs `ansible.builtin.shell`
- Variable names expected (`bastion_host`, `student_user`, etc.)

Always ask: "Is there a reference lab that does something similar?"

### 4. **Iterate Based on Corrections**
This session had ~8 redirections:
1. "Don't inline everything" → OK, call helper scripts
2. "Don't copy files to showroom repo" → OK, use source repo
3. "No, scripts are on bastion already" → OK, just call them
4. "You're missing the add_host pattern" → OK, fixing
5. "Don't create new scripts" → OK, removed
6. "Just call existing scripts" → OK, final approach

**Lesson**: Don't be defensive about corrections — each one is clarifying the actual need.

### 5. **Stub Files Are OK**
User was fine with `setup.yml` being a stub placeholder:
```yaml
tasks:
  - name: Setup placeholder
    ansible.builtin.debug:
      msg: "Module 01 setup - to be implemented"
```

Not everything needs to be fully implemented on first pass.

### 6. **Consistent Patterns Across Modules**
Once Module 1 was agreed upon, applying same pattern to Modules 2-4 was straightforward:
- Same SSH inventory build
- Same script execution pattern
- Just change module number in paths

### 7. **Git Commits Should Be Descriptive**
Final commit message explained:
- What was added
- How it works (SSH from pod to bastion)
- Why (runs existing scripts)

This helps reviewers understand without reading the entire diff.

---

## Testing Checklist (Next Steps)

When the user orders the lab:

**Pre-flight**:
- [ ] Verify scripts exist at `$HOME/lab-assets/` on bastion
- [ ] Verify `oc` CLI works on bastion
- [ ] Verify environment variables are set (`echo $GUID`, `echo $CLUSTER_DOMAIN`)

**Module 1 Test**:
- [ ] Click "Solve" button in Showroom
- [ ] Verify zt-runner connects to bastion via SSH
- [ ] Verify `solve-module-1.sh` executes successfully
- [ ] Check RHTPA is installed and accessible
- [ ] Click "Validate" button
- [ ] Verify all 5 validation checks pass

**Debug if failures**:
```bash
# On bastion, check logs
cat $HOME/lab-assets/solve-module-1.sh  # Does script exist?
bash -x $HOME/lab-assets/solve-module-1.sh  # Run manually with debug
oc get keycloakrealmimport -n sso  # Check if resources were created
oc logs -n showroom <zt-runner-pod>  # Check zt-runner logs
```

---

## Potential Issues & Mitigations

### Issue 1: SSH Connection Fails
**Symptom**: "Failed to connect to bastion"  
**Causes**:
- `bastion_host` not set or incorrect
- Firewall blocking SSH from zt-runner pod
- Wrong credentials

**Fix**:
```yaml
# Verify in AgV userdata
agnosticd_user_data:
  bastion_host: "{{ bastion_public_hostname }}"  # Must be reachable from pod
```

### Issue 2: Scripts Not Found
**Symptom**: "bash: /home/lab-user/lab-assets/solve-module-1.sh: No such file or directory"  
**Cause**: Scripts not deployed by AgV workload

**Fix**: Ensure AgV has a role that templates scripts to bastion, e.g.:
```yaml
- name: Copy solve scripts to bastion
  ansible.builtin.template:
    src: solve-module-1.sh.j2
    dest: "{{ ansible_env.HOME }}/lab-assets/solve-module-1.sh"
    mode: '0755'
```

### Issue 3: Scripts Fail with Missing Commands
**Symptom**: "oc: command not found" or "jq: command not found"  
**Cause**: Bastion missing required tools

**Fix**: AgV workload must install dependencies:
```yaml
- name: Install required packages on bastion
  ansible.builtin.package:
    name:
      - jq
      - curl
    state: present
```

### Issue 4: Environment Variables Not Available
**Symptom**: Script fails with "CLUSTER_DOMAIN: unbound variable"  
**Cause**: Variables not passed from AgV to zt-runner to bastion

**Fix 1** (AgV side): Set in userdata
```yaml
agnosticd_user_data:
  CLUSTER_DOMAIN: "{{ openshift_cluster_ingress_domain }}"
```

**Fix 2** (Playbook side): Export in shell task
```yaml
- name: Run solve script
  ansible.builtin.shell: |
    export CLUSTER_DOMAIN="{{ lookup('env', 'CLUSTER_DOMAIN') }}"
    export GUID="{{ lookup('env', 'GUID') }}"
    bash $HOME/lab-assets/solve-module-1.sh
```

---

## Alternative Approaches Considered (But Rejected)

### Approach 1: ansible.builtin.script
**From reference example**: Copy script from showroom repo to bastion and execute

```yaml
- name: Run solve-module2.sh
  ansible.builtin.script:
    executable: /bin/bash
    cmd: "{{ playbook_dir }}/solve-module2.sh"
```

**Why rejected**: User's scripts are already on bastion (deployed by AgV workload), not in showroom repo.

**When to use**: If scripts live in the showroom repo and need to be copied to bastion each time.

### Approach 2: Inline All Logic
**What it would look like**: Put entire bash script content in playbook

```yaml
- name: Solve Module 1
  ansible.builtin.shell: |
    #!/bin/bash
    # ... 200 lines of bash ...
```

**Why rejected**: 
- Duplicates existing scripts
- Harder to maintain (two sources of truth)
- Defeats purpose of having separate solve scripts

**When to use**: Simple one-liners or when no existing scripts exist.

### Approach 3: Pure Ansible Modules
**What it would look like**: Use `kubernetes.core.k8s` module for all operations

```yaml
- name: Create Keycloak Realm
  kubernetes.core.k8s:
    state: present
    definition: "{{ lookup('template', 'keycloak-realm.yml.j2') }}"
```

**Why rejected**: 
- Massive rewrite effort
- User already has working bash scripts
- Bash scripts are easier for non-Ansible users to understand

**When to use**: Greenfield ZT grading with no existing automation.

---

## Success Criteria Met

✅ **Scaffold created** — `site.yml` and `ui-config.yml` updated for ZT  
✅ **All 4 modules implemented** — solve.yml and validation.yml for each  
✅ **Simple pattern** — Just calls existing bastion scripts  
✅ **No duplication** — Doesn't recreate scripts or logic  
✅ **Committed and pushed** — Code in main branch  
✅ **Documentation created** — This session log

---

## References

- **ZT Grading Reference**: https://github.com/rhpds/ocp-zt-dedicated-showroom
- **Scripts Source**: https://github.com/rhpds/rhpds.build-secured-dev-workflows
- **Showroom Repo**: https://github.com/rhpds/unified-devsecops-delivery-showroom
- **FTL Skills**: `/ftl:rhdp-lab-validator` in Claude Code
- **Nookbag UI Bundle**: https://github.com/rhpds/nookbag/releases/tag/v0.0.3

---

## Final Notes

**What worked well**:
- User had clear vision once architecture was understood
- Iterative corrections led to clean final solution
- Consistent pattern across all modules
- Minimal code, maximum reuse

**What could have been faster**:
- Earlier clarification of architecture (pod + bastion hybrid)
- Asking for reference examples sooner
- Not assuming "showroom on OpenShift" meant tenant lab

**For future similar tasks**:
1. Ask about architecture upfront (diagram if needed)
2. Request reference examples immediately
3. Start with simplest viable approach
4. Iterate based on user corrections
5. Keep it minimal — don't over-engineer

---

**Session Duration**: ~2 hours  
**Commits**: 2 (scaffold + implementation)  
**Files Modified**: 10 (site.yml, ui-config.yml, 8 playbooks)  
**Lines of Code**: ~200 total

**Status**: ✅ Ready for testing on live environment
