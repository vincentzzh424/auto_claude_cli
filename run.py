import argparse
import subprocess
import os
import sys
import json
import re
import time
from datetime import datetime
from graphlib import TopologicalSorter
import urllib.request
import urllib.error

DEFAULT_LANGUAGE = "Python"
PROGRESS_FILE = "PROGRESS.md"
RETRY_WAIT_DEFAULT = 600  # 10 minutes

g_retry_wait = RETRY_WAIT_DEFAULT

# ================= Configuration & Utilities =================

class ConsoleStyle:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'


def print_step(stage, msg):
    """Prints a stylized stage header and message to the console."""
    print(f"{ConsoleStyle.HEADER}[{datetime.now().strftime('%H:%M:%S')}] {ConsoleStyle.BLUE}== {stage} =={ConsoleStyle.ENDC}")
    print(f"{ConsoleStyle.GREEN}{msg}{ConsoleStyle.ENDC}\n")

def parse_json_file(filepath):
    """Safely reads and parses a JSON file, handling potential Markdown code blocks."""
    if not os.path.exists(filepath):
        return None
    with open(filepath, 'r', encoding='utf-8') as f:
        text = f.read()
    # Remove Markdown code block syntax if present
    text = re.sub(r'```json\s*|```', '', text)
    try:
        return json.loads(text)
    except:
        return None

# ================= API Health Check =================

def read_claude_settings():
    """Read Claude CLI settings from ~/.claude/settings.json."""
    settings_path = os.path.expanduser("~/.claude/settings.json")
    if not os.path.exists(settings_path):
        return None
    try:
        with open(settings_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return None

def check_api_health():
    """
    Pre-flight check: verify the model API is responsive.
    Blocks and retries indefinitely on rate limit (429).
    """
    settings = read_claude_settings()
    if not settings:
        return

    env = settings.get("env", {})
    base_url = env.get("ANTHROPIC_BASE_URL", "")
    api_key = env.get("ANTHROPIC_AUTH_TOKEN", "")
    model = env.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

    if not base_url or not api_key:
        return

    endpoint = f"{base_url.rstrip('/')}/v1/messages"
    payload = json.dumps({
        "model": model,
        "max_tokens": 1,
        "messages": [{"role": "user", "content": "hi"}]
    }).encode('utf-8')

    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01"
    }

    first_attempt = True
    while True:
        try:
            req = urllib.request.Request(endpoint, data=payload, headers=headers, method="POST")
            urllib.request.urlopen(req, timeout=30)
            if not first_attempt:
                print(f"\n✅ API recovered! Continuing...\n")
            return
        except urllib.error.HTTPError as e:
            if e.code == 429:
                if first_attempt:
                    print(f"{ConsoleStyle.YELLOW}⏳ API rate limited (429).{ConsoleStyle.ENDC}")
                    first_attempt = False
                print(f"   Waiting {g_retry_wait}s for quota reset...")
                countdown(g_retry_wait)
            else:
                body = e.read().decode('utf-8', errors='replace')[:200]
                print(f"⚠️  API error {e.code}: {body}")
                return
        except Exception as e:
            print(f"⚠️  Health check failed: {e}")
            return

def countdown(seconds):
    """Print a live countdown timer."""
    try:
        for remaining in range(seconds, 0, -1):
            mins, secs = divmod(remaining, 60)
            sys.stdout.write(f"\r   ⏳ {mins:02d}:{secs:02d} remaining... (Ctrl+C to abort)")
            sys.stdout.flush()
            time.sleep(1)
        sys.stdout.write("\r" + " " * 70 + "\r")
        sys.stdout.flush()
    except KeyboardInterrupt:
        print(f"\n{ConsoleStyle.FAIL}❌ Aborted by user during rate limit wait.{ConsoleStyle.ENDC}")
        sys.exit(1)

# ================= Progress Manager =================

class ProgressManager:
    """Tracks pipeline progress in PROGRESS.md for resume support."""

    STATUS_MAP = {'x': 'done', '~': 'active', '!': 'failed', ' ': 'pending'}
    CHAR_MAP = {'done': 'x', 'active': '~', 'failed': '!', 'pending': ' '}

    def __init__(self):
        self.idea = ""
        self.started = ""
        self.stages = []  # [(id, name, status, timestamp)]

    def load(self):
        """Load from PROGRESS.md. Returns True if valid progress found."""
        if not os.path.exists(PROGRESS_FILE):
            return False
        try:
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                content = f.read()

            # Parse meta
            idea_m = re.search(r'\*\*Idea\*\*:\s*(.+)', content)
            started_m = re.search(r'\*\*Started\*\*:\s*(.+)', content)
            if idea_m:
                self.idea = idea_m.group(1).strip()
            if started_m:
                self.started = started_m.group(1).strip()

            # Parse stage lines: "- [x] stage_id Name @ timestamp"
            self.stages = []
            for line in content.split('\n'):
                m = re.match(
                    r'^\- \[([ x~!])\] (\S+)\s+(.+?)(?:\s+@\s+(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}))?\s*$',
                    line.strip()
                )
                if m:
                    sc, sid, name, ts = m.groups()
                    self.stages.append((sid, name.strip(), self.STATUS_MAP.get(sc, 'pending'), ts or ""))

            return len(self.stages) > 0
        except Exception as e:
            print(f"⚠️  Failed to parse {PROGRESS_FILE}: {e}")
            return False

    def create(self, idea):
        """Create fresh PROGRESS.md."""
        self.idea = idea
        self.started = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.stages = [
            ("-1",   "Requirement Research", "pending", ""),
            ("-0.5", "Brainstorming",        "pending", ""),
            ("0",    "Product Definition",   "pending", ""),
            ("1",    "Architecture",          "pending", ""),
            ("2",    "Dependency Analysis",   "pending", ""),
            ("3",    "Development Loop",      "pending", ""),
            ("4",    "Refactoring",           "pending", ""),
            ("5",    "Final Acceptance",      "pending", ""),
        ]
        self.save()
        print(f"📝 Created {PROGRESS_FILE}")

    def is_done(self, stage_id):
        for sid, _, status, _ in self.stages:
            if sid == stage_id:
                return status == "done"
        return False

    def set_active(self, stage_id):
        self._update(stage_id, "active")

    def set_done(self, stage_id):
        self._update(stage_id, "done")

    def set_failed(self, stage_id):
        self._update(stage_id, "failed")

    def expand_stage3(self, build_order):
        """After dependency analysis, replace Stage 3 block with per-module sub-stages."""
        # Preserve per-step completion status
        old_status = {}
        for sid, _, status, ts in self.stages:
            if "|" in sid:
                old_status[sid] = (status, ts)

        # Remove Stage 3 block and old module sub-stages
        self.stages = [s for s in self.stages if s[0] != "3" and "|" not in s[0]]

        # Build new module sub-stages
        module_stages = []
        for module_name in build_order:
            for step, desc in [("3.1", "Build"), ("3.2", "Integrate"), ("3.3", "Verify")]:
                key = f"{step}|{module_name}"
                if key in old_status:
                    module_stages.append((key, f"{desc}: {module_name}", *old_status[key]))
                else:
                    module_stages.append((key, f"{desc}: {module_name}", "pending", ""))

        # Insert before stage 4/5
        insert_idx = len(self.stages)
        for i, (sid, _, _, _) in enumerate(self.stages):
            if sid in ("4", "5"):
                insert_idx = i
                break
        self.stages = self.stages[:insert_idx] + module_stages + self.stages[insert_idx:]
        self.save()

    def _update(self, stage_id, status):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for i, (sid, name, s, ts) in enumerate(self.stages):
            if sid == stage_id:
                self.stages[i] = (sid, name, status, now if status in ("done", "active") else ts)
                break
        self.save()

    def save(self):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
            f.write("# Project Progress\n\n")
            f.write(f"- **Idea**: {self.idea}\n")
            f.write(f"- **Started**: {self.started}\n")
            f.write(f"- **Updated**: {now}\n\n")
            f.write("## Pipeline\n\n")
            for sid, name, status, ts in self.stages:
                c = self.CHAR_MAP.get(status, ' ')
                ts_str = f" @ {ts}" if ts else ""
                f.write(f"- [{c}] {sid} {name}{ts_str}\n")

    def print_summary(self):
        """Print a quick progress summary."""
        done = sum(1 for _, _, s, _ in self.stages if s == "done")
        total = len(self.stages)
        active = [name for _, name, s, _ in self.stages if s == "active"]
        failed = [name for _, name, s, _ in self.stages if s == "failed"]
        print(f"   Progress: {done}/{total} stages completed")
        if active:
            print(f"   Active: {', '.join(active)}")
        if failed:
            print(f"   Failed: {', '.join(failed)}")
        print()

# ================= Claude Agent Driver =================

def execute_claude_agent(prompt, context_files=[], allow_fail=False, max_retries=2):
    """
    Invokes the Claude CLI via a temporary instruction file to bypass shell length limits.
    Includes pre-flight API health check with rate limit retry.
    """
    # Pre-flight health check
    check_api_health()

    # 1. Build context from files
    context_str = ",".join(context_files)

    # 2. Construct the massive system instruction
    massive_prompt_content = f"""
    [SYSTEM INSTRUCTION]
    You are a HEADLESS, NON-CONVERSATIONAL software agent.
    1. DO NOT talk. DO NOT explain.
    2. Read the instructions below and EXECUTE them immediately using tools.

    [CONTEXT FILES]
    {context_str}

    [USER TASK]
    {prompt}
    """

    # 3. Write instruction to a buffer file
    temp_instruction_file = "_claude_instruction_buffer.txt"
    with open(temp_instruction_file, "w", encoding="utf-8") as f:
        f.write(massive_prompt_content)

    print(f"🤖 (Instructions written to {temp_instruction_file}, Size: {len(massive_prompt_content)} chars)")

    # 4. Trigger Claude to read the buffer file
    trigger_prompt = f"Read the file '{temp_instruction_file}' and execute the [USER TASK] inside it immediately. Do not converse."

    cmd = [
        "claude",
        "--dangerously-skip-permissions",
        "-p", trigger_prompt ,"--verbose"
    ]

    is_windows = (os.name == 'nt')

    for attempt in range(max_retries + 1):
        try:
            subprocess.run(cmd, check=True, shell=is_windows)

            # Optional: Clean up buffer file
            # if os.path.exists(temp_instruction_file):
            #     os.remove(temp_instruction_file)
            return

        except subprocess.CalledProcessError:
            if attempt < max_retries:
                print(f"{ConsoleStyle.YELLOW}⚠️ Claude failed, retrying ({attempt+1}/{max_retries})...{ConsoleStyle.ENDC}")
                time.sleep(3)
            else:
                if not allow_fail:
                    sys.exit(1)

# ================= STAGE -1: Requirement Research =================

def stage_requirement_research(raw_idea):
    print_step("STAGE -1", "Requirement Research & Analysis (Researcher)")

    prompt = f"""
    [ROLE]: Senior Product Researcher
    [IDEA]: {raw_idea}
    [LANGUAGE]: USE IDEA SAME LANGUAGE

    Please conduct comprehensive requirement research and analysis for this idea.

    RESEARCH SCOPE:
    1. **Market Research**: Identify similar products, competitors, and market trends
    2. **User Analysis**: Define target users, user personas, and use cases
    3. **Technical Feasibility**: Identify technical challenges, required technologies, and potential solutions
    4. **Best Practices**: Research industry standards, design patterns, and best practices for similar systems
    5. **Potential Risks**: Identify technical, business, and implementation risks
    6. **Feature Prioritization**: Suggest MVP features vs. future enhancements based on research

    OUTPUT REQUIREMENTS:
    - Generate `research.md` with all research findings
    - Include citations or references to industry standards where applicable
    - Provide actionable insights that will guide product design

    NOTE: This is RESEARCH phase. Do NOT write code or design the system yet. Focus on gathering information and insights.
    """
    execute_claude_agent(prompt)

# ================= STAGE -0.5: Brainstorming & User Scenarios =================

def stage_brainstorming(raw_idea):
    print_step("STAGE -0.5", "User Brainstorming & Scenario Design (User Personas)")

    prompt = f"""
    [ROLE]: User Experience Researcher & Scenario Designer
    [IDEA]: {raw_idea}
    [LANGUAGE]: USE IDEA SAME LANGUAGE
    [CONTEXT]: Based on research findings from `research.md`

    Conduct a multi-perspective brainstorming session by role-playing different target user personas.

    OUTPUT REQUIREMENTS:
    Generate `BRAIN.md` with the following sections:

    1. **User Personas** (3-5 distinct personas):
       - Name, age, occupation
       - Technical proficiency level
       - Primary goals and pain points
       - Attitude toward the product concept

    2. **Brainstorming Discussion**:
       - Simulated dialogue between personas discussing the idea
       - Each persona brings their unique perspective
       - Conflicts, agreements, and insights from the discussion
       - Different expectations and use cases emerge

    3. **User Scenarios** (5-8 scenarios):
       - For each scenario: context, motivation, expected outcome
       - Cover different personas and use cases
       - Include edge cases and unusual situations

    4. **Requirements List from User Perspectives**:
       - Must-have requirements (pain points that must be solved)
       - Nice-to-have features (delighters)
       - Anti-requirements (things users explicitly don't want)

    5. **Ideal Future Scenarios**:
       - Describe 2-3 "perfect world" scenarios where the product exceeds expectations
       - What would delight users beyond basic functionality
       - Long-term vision possibilities

    CRITICAL: This brainstorming should feel REAL. Each persona should have a distinct voice, real concerns, and valid perspectives. The discussion should reveal insights that wouldn't be obvious from a single perspective.

    NOTE: Do NOT write code. Only produce the BRAIN.md documentation.
    """
    execute_claude_agent(prompt, context_files=["research.md"])

# ================= STAGE 0: Product Definition =================

def stage_product_definition(raw_idea):
    print_step("STAGE 0", "Product Requirement Analysis (PM)")

    prompt = f"""
    [ROLE]: Senior Product Manager (PM)
    [IDEA]: {raw_idea}
    [LANGUAGE]: USE IDEA SAME LANGUAGE

    Please perform a deep requirement analysis on this idea, BASED on the research findings AND user brainstorming insights.

    OUTPUT REQUIREMENTS:
    1. `PRD.md` (Product Requirement Doc): Detailed feature list, tech stack confirmation (Default: {DEFAULT_LANGUAGE}).
       - MUST incorporate insights and findings from `research.md`
       - MUST leverage user personas, scenarios, and requirements from `BRAIN.md`
       - Align product features with research-backed user needs
       - Prioritize features based on user persona discussions
       - Consider technical feasibility identified in research
    2. `DATA_FLOW.md` (Data Flow Design): Data flow diagrams and core data structures.
       - Design data flows considering technical constraints from research
       - Consider user journey scenarios from BRAIN.md

    CRITICAL: Your PRD should be grounded in both the research findings from `research.md` AND the user insights from `BRAIN.md`. Leverage the market analysis, user personas, technical feasibility insights, and multi-perspective brainstorming to create a well-informed product specification.

    NOTE: Do NOT write code yet. Only produce documentation.
    """
    execute_claude_agent(prompt, context_files=["research.md", "BRAIN.md"])

# ================= STAGE 1: System Architecture =================

def stage_system_architecture():
    print_step("STAGE 1", "System Architecture & CLI Design (Architect)")

    prompt = f"""
    [ROLE]: System Architect
    [TASK]: Design the code architecture based on the PRD.
    [LANGUAGE]: USE PRD.md SAME LANGUAGE

    Read `PRD.md` and `DATA_FLOW.md`.

    OUTPUT REQUIREMENTS:
    1. Generate `architecture.json`.
       **CRITICAL**: Even if this is a Web Project, it must be a "CLI-First" architecture.
       The `entry_point` must handle command-line arguments to invoke underlying services directly for testing.

       Format Example:
       {{
           "modules": {{ ... }},
           "entry_point": "main.py",
           "cli_design": {{
               "run_server": "Start main service/web server",
               "test_api": "Call API function directly via JSON args (No network)",
               "inspect_db": "Print DB stats"
           }}
       }}

    2. Generate `requirements.txt` and install dependencies.
    """
    execute_claude_agent(prompt, context_files=["PRD.md", "DATA_FLOW.md"])

# ================= STAGE 2: Dependency Analysis =================

def stage_dependency_analysis():
    print_step("STAGE 2", "Compute Development Path (Topological Sort)")

    arch = parse_json_file("architecture.json")
    if not arch:
        print("❌ Unable to read architecture.json. Check Stage 1 output.")
        sys.exit(1)

    modules = arch.get('modules', {})
    sorter = TopologicalSorter()

    for name, info in modules.items():
        sorter.add(name, *info.get('dependencies', []))

    try:
        build_order = list(sorter.static_order())
        print(f"🔨 Build Order: {' -> '.join(build_order)}")
        return build_order, arch
    except Exception as e:
        print(f"{ConsoleStyle.FAIL}❌ Circular Dependency Error: {e}{ConsoleStyle.ENDC}")
        sys.exit(1)

# ================= STAGE 3: Development Loop =================

def stage_development_loop(build_order, arch_data, progress):
    """
    Core CI/CD Loop: Develop -> Integrate -> Verify
    Skips completed sub-steps based on progress.
    """
    modules_info = arch_data['modules']
    entry_point = arch_data.get('entry_point', 'main.py')

    # Reconstruct completed_modules from progress
    completed_modules = []
    for module_name in build_order:
        if progress.is_done(f"3.3|{module_name}"):
            completed_modules.append(module_name)

    for module_name in build_order:
        info = modules_info[module_name]

        # --- Step 3.1: Build (Dev) ---
        if not progress.is_done(f"3.1|{module_name}"):
            progress.set_active(f"3.1|{module_name}")
            print_step("STAGE 3.1 (Dev)", f"Building Module: {module_name}")
            build_single_module(module_name, info)
            progress.set_done(f"3.1|{module_name}")

        if module_name not in completed_modules:
            completed_modules.append(module_name)

        # --- Step 3.2: Integrate (Ops) ---
        if not progress.is_done(f"3.2|{module_name}"):
            progress.set_active(f"3.2|{module_name}")
            print_step("STAGE 3.2 (Integration)", f"Integrating {module_name} into {entry_point}")
            integrate_module_into_entry(entry_point, completed_modules)
            progress.set_done(f"3.2|{module_name}")

        # --- Step 3.3: Verify (QA) ---
        if not progress.is_done(f"3.3|{module_name}"):
            progress.set_active(f"3.3|{module_name}")
            print_step("STAGE 3.3 (Verification)", f"Verifying {module_name} via CLI")
            verify_module_via_cli(entry_point, module_name)
            progress.set_done(f"3.3|{module_name}")

def build_single_module(name, info):
    prompt = f"""
    [ROLE]: Senior {DEFAULT_LANGUAGE} Developer
    [DOCS]: PRD.md
    [ARCH]: architecture.json
    [TASK]: Develop the module `{name}` defined in modules.
    [COMMENT LANGUAGE]: USE PRD.md SAME LANGUAGE

    REQUIREMENTS:
    1. **NO MOCK**: Dependencies are ready. Import and use them directly.
    2. **IMPLEMENTATION**: Write real, robust code.
    3. **UNIT TEST**: Write `tests/test_{name}.py` and execute it to ensure it passes.
    """
    execute_claude_agent(prompt)

def integrate_module_into_entry(entry_point, completed_modules_list):
    """
    Updates the main entry point incrementally.
    """
    prompt = f"""
    [ROLE]: Integration Engineer
    [TASK]: Update the entry point file `{entry_point}`
    [DOCS]: PRD.md
    [ARCH]: architecture.json
    [COMMENT LANGUAGE]: USE PRD.md SAME LANGUAGE
    [READY MODULES]: {completed_modules_list}

    INSTRUCTIONS:
    1. Use `argparse` for CLI routing.
    2. **ONLY Import and Register functionality from [READY MODULES].** Do NOT import modules that are not built yet.
    3. Ensure Test Mode support: e.g., `python {entry_point} test --target [function] --args [json]`.
    4. Expose at least one core testable function for the latest module.
    """
    execute_claude_agent(prompt)

def verify_module_via_cli(entry_point, module_name):
    """
    Acceptance test for the new module via the CLI entry point.
    """
    prompt = f"""
    [ROLE]: QA Engineer and Senior {DEFAULT_LANGUAGE} Developer
    [DOCS]: PRD.md
    [ARCH]: architecture.json
    [COMMENT LANGUAGE]: USE PRD.md SAME LANGUAGE
    [TASK]: Verify that `{module_name}` is successfully integrated into `{entry_point}` and Fix exist bugs.

    INSTRUCTIONS:
    1. Construct a {DEFAULT_LANGUAGE} CLI command. Example: `python {entry_point} test --target [belonging_to_{module_name}] ...`
    2. Execute the command.
    3. Confirm the output is correct (Exit Code 0 and valid JSON/Text output).
    """
    execute_claude_agent(prompt)

# ================= STAGE 4: Refactoring & Review =================

def stage_refactoring(arch_data):
    print_step("STAGE 4", "System Refactoring & Code Review (Refactoring Lead)")

    prompt = f"""
    [ROLE]: System Refactoring Lead
    [TASK]: Review code design, simplify unreasonable modules, and ensure a solid foundation.
    [DOCS]: PRD.md
    [ARCH]: architecture.json
    [COMMENT LANGUAGE]:USE PRD.md SAME LANGUAGE

    EXECUTION STEPS:
    1. READ and ANALYZE the provided source files.
    2. IDENTIFY 1-3 specific areas for improvement (e.g., duplicated logic, messy imports, hardcoded values).
    3. REFACTOR (Rewrite) the code to be cleaner and more professional.
    4. **CRITICAL**: After refactoring, you MUST run project tests (e.g., `pytest` or `python main.py test`) to ensure functionality is intact.

    [SAFETY RULE]
    If tests fail after your refactor, you MUST fix the code immediately.

    EXECUTE REFACTORING NOW.
    """
    execute_claude_agent(prompt)

# ================= STAGE 5: Final Acceptance =================

def stage_final_acceptance(entry_point):
    print_step("STAGE 5", "Final System Acceptance Test")

    prompt = f"""
    [ROLE]: Acceptance Test Lead
    [TASK]: End-to-End System Test
    [DOCS]: PRD.md
    [LANGUAGE]: USE PRD.md SAME LANGUAGE

    All modules are developed and integrated. Verify their collaboration.

    INSTRUCTIONS:
    1. Run the project using standard {DEFAULT_LANGUAGE} commands (e.g., `python {entry_point} run`).
    2. Or run a complex test command involving multiple module interactions.
    3. Check for any remaining TODOs, 'Pass', or Mock code. Point them out or fix them.
    4. Output the final "PROJECT READY" confirmation.
    """
    execute_claude_agent(prompt)

# ================= Main Entry =================

def main():
    global g_retry_wait

    parser = argparse.ArgumentParser(description="Auto Claude - Autonomous Software Factory (Resume Edition)")
    parser.add_argument("raw_idea", nargs="?", help="The initial software idea (optional when resuming)")
    parser.add_argument("--force", action="store_true", help="Force fresh start, ignore existing progress")
    parser.add_argument("--retry-wait", type=int, default=RETRY_WAIT_DEFAULT,
                        help=f"Seconds to wait on API rate limit (default: {RETRY_WAIT_DEFAULT})")
    args = parser.parse_args()

    g_retry_wait = args.retry_wait

    progress = ProgressManager()

    # --- Determine mode: resume or fresh ---
    resuming = False
    if not args.force and progress.load():
        idea = progress.idea
        print(f"{ConsoleStyle.CYAN}📂 Resuming project: {idea[:60]}...{ConsoleStyle.ENDC}")
        progress.print_summary()
        resuming = True
    elif args.raw_idea:
        if args.force and os.path.exists(PROGRESS_FILE):
            print(f"{ConsoleStyle.YELLOW}🔄 --force: starting fresh, overwriting progress.{ConsoleStyle.ENDC}")
        idea = args.raw_idea
        progress.create(idea)
    else:
        print(f"{ConsoleStyle.FAIL}❌ No idea provided and no progress file found.{ConsoleStyle.ENDC}")
        print(f"   Usage: python run.py \"your idea\"")
        print(f"   Or:    python run.py              (to resume)")
        sys.exit(1)

    print(f"Input Idea: {idea}\n")

    # --- Pipeline with Progress Tracking ---

    # Stage -1: Requirement Research
    if not progress.is_done("-1"):
        progress.set_active("-1")
        stage_requirement_research(idea)
        progress.set_done("-1")

    # Stage -0.5: Brainstorming
    if not progress.is_done("-0.5"):
        progress.set_active("-0.5")
        stage_brainstorming(idea)
        progress.set_done("-0.5")

    # Stage 0: Product Definition
    if not progress.is_done("0"):
        progress.set_active("0")
        stage_product_definition(idea)
        progress.set_done("0")

    # Stage 1: Architecture
    if not progress.is_done("1"):
        progress.set_active("1")
        stage_system_architecture()
        progress.set_done("1")

    # Stage 2: Dependency Analysis (always runs — just local parsing, no Claude call)
    build_order, arch_data = stage_dependency_analysis()
    if not progress.is_done("2"):
        progress.set_done("2")

    # Expand Stage 3 into per-module sub-stages (idempotent, preserves done status)
    progress.expand_stage3(build_order)

    # Stage 3: Development Loop (checks per-module per-step progress)
    stage_development_loop(build_order, arch_data, progress)

    # Stage 4: Refactoring
    if not progress.is_done("4"):
        progress.set_active("4")
        stage_refactoring(arch_data)
        progress.set_done("4")

    # Stage 5: Final Acceptance
    entry_point = arch_data.get('entry_point', 'main.py')
    if not progress.is_done("5"):
        progress.set_active("5")
        stage_final_acceptance(entry_point)
        progress.set_done("5")

    print_step("DONE", "✅ Project Construction Complete. All modules integrated and tested.")

if __name__ == "__main__":
    main()
