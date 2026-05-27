from playwright.sync_api import sync_playwright
import time
import json
import os

logs = []

def track(event_type, target, status, category=None):
    logs.append({
        "timestamp": time.strftime("%H:%M:%S"),
        "type": event_type,
        "target": target,
        "status": status,
        "category": category
    })

def analyze_inputs(page):
    try:
        inputs = page.locator("input")
        print(f"Found {inputs.count()} input fields")
        
        for i in range(inputs.count()):
            inputs.nth(i).fill("test")
            track("INPUT", f"input_{i}", "success", "INPUT_FIELD")
    except Exception as e:
        track("INPUT", "unknown_input", f"failed: {e}", "FRONTEND_ERROR")

def take_failure_screenshot(page, reason="unknown"):
    """Take screenshot only for important issues"""
    try:
        os.makedirs("screenshots", exist_ok=True)
        timestamp = str(int(time.time()))
        filename = f"screenshots/failure_{reason}_{timestamp}.png"
        
        page.screenshot(path=filename)
        print(f"Screenshot saved: {filename}")
        track("SCREENSHOT", filename, "captured", "FAILURE_EVIDENCE")
        return filename
    except Exception as e:
        print(f"Could not take screenshot: {e}")
        return None


def safe_click(page, button, button_text):
    """Click button safely with retry and error handling"""
    try:
        if not button.is_enabled(timeout=1000):
            track("CLICK", f"button '{button_text}'", "warning: disabled", "DISABLED_ELEMENT")
            return False, "disabled"

        button.click(timeout=4000)
        try:
            page.wait_for_load_state("domcontentloaded", timeout=3000)
        except:
            pass
        return True, "clicked"
    except Exception as e:
        track("CLICK", button_text, f"failed: {e}", "BROKEN_INTERACTION")
        take_failure_screenshot(page, f"critical_click_failed_{button_text[:20]}")
        return False, "exception"


def detect_interaction_result(page, button_text, before_url, before_content):
    """Analyze what happened after click"""
    after_url = page.url
    
    try:
        after_content = page.content()
    except:
        after_content = ""

    if after_url != before_url:
        track("NAVIGATION", after_url, "success")
        return "navigation"

    elif before_content == after_content:
        track("PAGE_CHANGE", f"{button_text} did not change page", "warning", "BROKEN_INTERACTION")
        take_failure_screenshot(page, f"broken_interaction_{button_text[:25]}")
        return "broken"

    else:
        track("PAGE_CHANGE", f"{button_text} changed page", "success")
        return "success"


def discover_new_buttons(page, before_count, queue):
    """Add newly appeared buttons to queue"""
    after_count = page.locator("button").count()
    if after_count > before_count:
        track("DOM_CHANGE", "new button detected", "success")
        for i in range(before_count, after_count):
            try:
                new_button = page.locator("button").nth(i)
                new_text = new_button.inner_text(timeout=1500)
                print(f"Discovered new button: {new_text}")
                queue.append(new_button)
            except:
                print("Discovered new button but could not read text")
                track("BUTTON", "dynamic_button", "warning: unreadable", "STALE_LOCATOR")
                queue.append(new_button)
    return after_count


def analyze_buttons(page, original_url):
    """Main orchestrator - now much cleaner"""
    try:
        queue = []
        buttons = page.locator("button")
        queue.extend(buttons.nth(i) for i in range(buttons.count()))
            
        while queue:
            current_button = queue.pop(0)
            
            # Safe text extraction
            try:
                button_text = current_button.inner_text(timeout=2000)
            except:
                button_text = "[Could not read text - stale element]"
                track("CLICK", "unknown_button", "failed", "STALE_LOCATOR")
                continue

            print(button_text)

            before_url = page.url
            before_content = page.content()
            before_count = buttons.count()

            # Perform click
            click_success, click_status = safe_click(page, current_button, button_text)

            if not click_success and click_status == "disabled":
                continue

            # Analyze what happened
            if click_success:
                detect_interaction_result(page, button_text, before_url, before_content)

            # Discover new buttons
            discover_new_buttons(page, before_count, queue)

            print(page.url)
        
    except Exception as e:
        track("CLICK", "button_analysis", f"failed: {e}", "FRONTEND_ERROR")
        print(f"Critical error in button analysis: {e}")
        take_failure_screenshot(page, "critical_button_error")

def generate_summary(execution_time):
    print("\n" + "="*65)
    print("                    FLOWRA ANALYSIS REPORT")
    print("="*65)

    frontend_errors = [log for log in logs if log.get("category") == "FRONTEND_ERROR"]
    broken_interactions = [log for log in logs if log.get("category") == "BROKEN_INTERACTION"]
    stale_locators = [log for log in logs if log.get("category") == "STALE_LOCATOR"]

    score = 100
    score -= len(frontend_errors) * 12
    score -= len(broken_interactions) * 10
    score -= len(stale_locators) * 6
    score = max(score, 0)

    if score >= 85:
        grade = "Excellent"
    elif score >= 70:
        grade = "Good"
    elif score >= 50:
        grade = "Needs Improvement"
    else:
        grade = "Critical"

    print(f"\nScore: {score}/100")
    print(f"Grade: {grade}")
    print(f"Execution Time: {execution_time} seconds\n")

    if frontend_errors:
        print("Frontend Errors:")
        for err in frontend_errors[:5]:
            print(f"   • {err['target']}")
    
    if broken_interactions:
        print("\nBroken Interactions:")
        for issue in broken_interactions[:6]:
            print(f"   • {issue['target']}")

    if stale_locators:
        print("\nStale Locators:")
        for stale in stale_locators[:4]:
            print(f"   • {stale['target']}")

    print("\n" + "="*65)

    return {
        "total_events": len(logs),
        "score": score,
        "grade": grade,
        "execution_time": execution_time,
        "frontend_errors": len(frontend_errors),
        "broken_interactions": len(broken_interactions),
        "stale_locators": len(stale_locators)
    }


# ===================== MAIN EXECUTION =====================
with sync_playwright() as p:
    track("SYSTEM", "browser launch", "success")
    
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    page.on("console", lambda msg: track(
        "CONSOLE", 
        msg.text, 
        msg.type, 
        "FRONTEND_ERROR" if msg.type == "error" else None
    ))
    
    page.goto("http://127.0.0.1:5500/test.html")
    track("NAVIGATION", "login page", "success")
    
    analyze_inputs(page)
    
    start = time.time()
    original_url = page.url
    
    analyze_buttons(page, original_url)
    
    end = time.time()
    execution_time = round(end - start, 2)

    summary = generate_summary(execution_time)

    report = {
        "logs": logs,
        "summary": summary,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }

    with open("flowra_report.json", "w") as f:
        json.dump(report, f, indent=4)

    print(f"\nReport saved to flowra_report.json")
    print(f"Screenshots saved only for BROKEN_INTERACTION & Critical Failures")

    browser.close()