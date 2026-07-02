
The most important distinction is:

The agent calls the tool. The tool runtime executes the tool’s code. The skill normally does not execute code by itself.

A skill usually guides the agent about which tool to call, when to call it, and how to verify the result.

Exact runtime relationship
User request
   ↓
Agent reasons about the request
   ↓
Agent reads or applies a skill
   ↓
Agent selects a tool
   ↓
Agent sends a tool call
   ↓
Tool runtime executes the tool code
   ↓
Tool returns a result
   ↓
Agent evaluates the result
For example:

SOP step:
Enter the website name and click Next.

Agent:
I need to complete and submit a form.

Skill:
1. Inspect the page.
2. Fill the field.
3. Verify the value.
4. Click Next.
5. Verify that the next page appears.

Agent calls:
inspect_page()

Tool runtime:
Executes the Python/Playwright code behind inspect_page()

Agent calls:
fill_text("Website name", "example.com")

Tool runtime:
Executes the Playwright fill operation.

Agent calls:
click_element("Next")

Tool runtime:
Executes the Playwright click operation.
The skill has influenced the sequence, but the agent made the tool calls.

Who operates the tool?
There are three different meanings of “operate.”

1. Who decides to use the tool?
The agent.

The agent decides:

I should now call click_element.
2. Who invokes or calls the tool?
Usually the agent runtime on behalf of the agent.

For example, the model produces something equivalent to:

{
  "tool": "click_element",
  "arguments": {
    "target": "Next"
  }
}
The orchestration system receives that request and invokes the registered function.

3. Who executes the code?
The tool runtime or application environment.

For example:

Python interpreter
FastAPI application
Playwright process
MCP server
GitHub Copilot extension
Claude Code runtime
Your own agent loop
The language model does not literally press the button itself. It requests a tool call. The runtime executes the underlying code.

So the precise answer is:

Agent chooses and calls
Tool runtime executes
Tool performs the external action
Does a skill call tools?
Conceptually, people often say:

“The skill calls the tool.”

But technically this depends on how you implement the skill.

There are two possible models.

Model A: Skill as instructions
This is the common .md skill model.

skill.md
contains instructions such as:

Before clicking:
- inspect the page
- verify the target
- click
- wait for the expected result
This Markdown file cannot independently execute anything.

The actual flow is:

Agent reads skill
Agent follows instructions
Agent calls tools
Therefore, in this model:

The skill does not call the tool directly. The agent calls the tool while following the skill.

This is likely the correct model for your tracer.md.

Model B: Skill as executable code
A skill can also be implemented as a Python function:

def complete_form(page, website_name):
    fill_result = fill_text(page, "Website name", website_name)
    if not fill_result.success:
        return fill_result

    click_result = click_element(page, "Next")
    if not click_result.success:
        return click_result

    return wait_for_page(page, "Banner Setup")
Here, the executable skill directly calls lower-level tools.

The flow becomes:

Agent calls skill
Skill code calls tools
Tool runtime executes everything
This is closer to a workflow or composite tool.

So the answer depends on what your “skill” actually is:

Skill type

Who calls the tool?

Markdown instruction skill

Agent

Prompt-based skill

Agent

Executable Python skill

Skill code

Workflow engine skill

Workflow engine

Composite tool presented as a skill

Composite tool code

For your Copilot/Codex skill files, the likely answer is:

The agent reads the skill and then calls the tools.

Why do we need a tool catalog when skills already exist?
Because a skill and a tool catalog solve different problems.

Skill answers
How should this kind of work be done?

Example:

To safely click a navigation button:

1. Inspect the current page.
2. Find a visible and enabled target.
3. Click it.
4. Wait for navigation.
5. Verify the expected page.
6. Capture diagnostics if verification fails.
This is procedural knowledge.

Tool catalog answers
What executable operations are actually available?

Example:

inspect_page
click_element
fill_text
wait_for_url
wait_for_text
capture_screenshot
This is an inventory of executable functions.

The skill may say:

Wait until the next page is ready.

But the tool catalog tells the agent whether it has:

wait_for_url
wait_for_selector
wait_for_text
wait_for_network_idle
and what inputs each tool accepts.

A skill cannot safely replace the tool catalog
Suppose tracer.md says:

Use the click tool to click the required element.
The agent still needs to know:

Is the tool called click, click_element, or browser_click?
Does it accept CSS selectors?
Does it accept accessible names?
What arguments are required?
Does it wait automatically?
What result does it return?
Can it click inside an iframe?
Is it currently enabled?
Is it permitted for this agent?
Which tool version is available?
That information belongs in the tool catalog or tool schema.

Example:

TOOLS = {
    "browser.click_element": {
        "description": "Click a visible enabled element",
        "inputs": {
            "role": "optional string",
            "name": "optional string",
            "selector": "optional string"
        },
        "output": {
            "success": "boolean",
            "url": "string",
            "error": "optional string"
        }
    }
}
The skill should not need to duplicate the complete technical contract for every tool.

Why do we need skills when a tool catalog already exists?
Because knowing what tools exist does not tell the agent how to combine them reliably.

Imagine a catalog containing:

inspect_page
fill_text
click_element
wait_for_selector
take_screenshot
The catalog tells the agent what each tool does.

But it does not necessarily tell the agent:

Inspect before clicking
Verify the field after filling
Do not assume a successful click means successful navigation
Wait for a specific postcondition
Retry only after re-inspecting the page
Stop if the page has changed unexpectedly
Capture evidence before returning failure
Without a skill, the agent may do this:

fill_text
click_element
mark step completed
With a skill, it should do this:

inspect_page
locate target
fill_text
verify field value
check button enabled
click_element
wait_for expected page
verify expected page
mark step completed
The tool catalog provides available actions.

The skill provides correct operating procedure.

Practical analogy
Consider a hospital.

Tool catalog
A list of available equipment:

MRI machine
X-ray machine
Blood pressure monitor
ECG machine
Ventilator
It describes what each machine does and how it is accessed.

Skill
Medical expertise:

How to diagnose chest pain
When to order an ECG
When an X-ray is appropriate
How to interpret results
When to escalate
Having a machine inventory does not make someone a cardiologist.

Having medical knowledge does not create an ECG machine.

They are complementary.

Where overlap happens
There can be some overlap between skills and tool catalogs.

A skill may contain:

Recommended tools:
- inspect_page
- click_element
- wait_for_text
And the tool catalog may contain:

click_element:
  use_when: a visible enabled element must be clicked
That overlap is acceptable, but they should still have different authoritative roles.

Use this rule:

Tool catalog is authoritative for:
- tool name
- tool availability
- input schema
- output schema
- version
- permissions
- implementation binding

Skill is authoritative for:
- sequence
- decision rules
- preconditions
- postconditions
- retries
- recovery
- domain-specific procedure
Could you use only a tool catalog?
Yes, for a small or simple agent.

For example:

User: Take a screenshot.
The agent sees take_screenshot in the catalog and calls it.

No skill is necessary.

A tool-catalog-only design works when:

Tasks are simple
Calls are independent
There are few tools
Failure recovery is straightforward
There is little domain knowledge
The model can reliably determine the sequence itself
But for your SOP automation, tool-catalog-only execution is risky because browser work requires:

Page inspection
State tracking
Waiting
Verification
Retry logic
Recovery
Evidence collection
That is where a skill helps.

Could you use only skills?
Only if the skills also contain or directly expose executable functions.

A pure Markdown skill without registered tools cannot interact with a browser.

It can say:

Click the Next button.
But unless some executable click operation is available, nothing will happen.

You could embed tool definitions inside every skill, but that creates problems:

The same tool gets duplicated across skills
Tool signatures can become inconsistent
Changing a tool requires editing many files
Permission control becomes difficult
Runtime discovery becomes difficult
Versioning becomes unclear
Agents may see conflicting definitions
Therefore, pure skill-only architecture is usually weak once the system grows.

The most useful architecture for your project
For your SOP automation project, separate these four layers.

Layer 1: Agent
Responsible for the overall task.

Read SOP
Track current step
Select skill
Call tools
Evaluate outcomes
Decide whether to continue
Layer 2: Skills
Reusable operating procedures.

Examples:

tracer
form_interaction
page_navigation
authentication
scan_completion_wait
failure_recovery
Layer 3: Tool catalog
Machine-readable list of the tools available to the agent.

Examples:

browser.inspect_page
browser.click
browser.fill
browser.select
browser.wait
browser.screenshot
browser.get_logs
Layer 4: Tool implementations
Actual Python/Playwright code.

async def click_element(...):
    await page.get_by_role(...).click()
The flow is:

Agent
  ↓ applies
Skill
  ↓ chooses from
Tool catalog
  ↓ invokes
Tool implementation
  ↓ executed by
Python / Playwright runtime
More precisely, since Markdown skills do not execute:

Agent reads skill
Agent looks at available tool definitions
Agent calls a registered tool
Runtime executes its implementation
Example from your exact scenario
Suppose the SOP says:

Enter the website URL and click Next.

Tool catalog
inspect_page
fill_field
read_field_value
click_element
wait_for_text
capture_screenshot
Skill
Form Submission Skill

1. Inspect the page.
2. Locate the field semantically.
3. Fill the field.
4. Read the field value back.
5. Confirm the submit button is enabled.
6. Click the button.
7. Wait for a page-specific success condition.
8. If the expected condition does not appear, do not mark success.
Agent execution
Agent reads the SOP step.
Agent applies Form Submission Skill.
Agent calls inspect_page.
Runtime executes inspect_page code.
Agent receives the page structure.

Agent calls fill_field.
Runtime executes Playwright fill code.
Agent receives success.

Agent calls read_field_value.
Runtime executes code.
Agent verifies the value.

Agent calls click_element.
Runtime executes Playwright click.

Agent calls wait_for_text("Banner Setup").
Runtime waits and returns success or timeout.

Agent decides whether the SOP step is complete.
This makes the ownership clear:

Skill defines the procedure.
Agent controls the process.
Tool catalog exposes available operations.
Tool runtime executes the code.
The simplest final distinction
Agent = caller and decision-maker

Skill = procedure the caller follows

Tool catalog = menu and technical contract of callable operations

Tool = implementation of an operation

Runtime = system that executes the implementation
You need both skills and a tool catalog when the agent must know both:

What it can do
How it should do it correctly
A catalog without skills gives the agent a box of equipment without a reliable method.

A skill without tools gives the agent instructions but no equipment.

