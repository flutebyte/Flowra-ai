from playwright.sync_api import sync_playwright
import time
import json

logs = []

def track(event_type, target, status, category=None):
    logs.append({
        "type": event_type,
        "target": target,
        "status": status,
        "category": category
    })

def analyze_inputs(page):
    try:
        inputs = page.locator("input")

        print(inputs.count())
        for i in range(inputs.count()):
            inputs.nth(i).fill("test")
            track("INPUT", f"input_{i}", "success")
    except Exception as e:
        track("INPUT", f"unknown_input", f"failed: {e}")

def analyze_buttons(page, original_url):
    try:
        queue = []

        buttons = page.locator("button")

        for i in range(buttons.count()):
            queue.append(buttons.nth(i))
            
        while queue:
            current_button = queue.pop(0)
            before = page.content()
            button_text = current_button.inner_text()
            print(button_text)

            before_count = buttons.count()

            if current_button.is_enabled():
                current_button.click()
                after_count = page.locator("button").count()
            else:
                track(
                    "CLICK",
                    f"button '{button_text}'",
                    "warning: disabled",
                    "DISABLED_ELEMENT"
                )
                continue

            if after_count > before_count:
                track("DOM_CHANGE", "new button detected", "success")
                # Add new buttons to the queue
                for i in range(before_count, after_count):
                    new_button= page.locator("button").nth(i)
                    print(
                        f"Discovered new button: "
                        f"{new_button.inner_text()}")
                    queue.append(new_button)

            if page.url != original_url:
                track("NAVIGATION", page.url, "success")

            after = page.content()
            if before != after:
                track("PAGE_CHANGE", f"{button_text} changed page", "success")
            else:
                track(
                    "PAGE_CHANGE",
                    f"{button_text} did not change page",
                    "warning",
                    "BROKEN_INTERACTION"
                )
            print(page.url)
        
    except Exception as e:
        track("CLICK", "button[type='submit']", f"failed: {e}")
        print(e)
    
def generate_summary(execution_time):
    frontend_errors = []
    interaction_issues = []
    recommendations = []
    score=100
    grade = "Critical"
    summary= {
        "total_events": len(logs),
        "successes": sum(1 for log in logs if log["status"] == "success"),
        "warnings": sum(1 for log in logs if log["status"].startswith("warning")),
        "failures": sum(1 for log in logs if log["status"].startswith("failed")),
    }
    for log in logs:
        if log["category"] == "BROKEN_INTERACTION":
            interaction_issues.append(log['target'])
            recommendation= f"{log['target']} may have broken click handling or missing UI response."
            if recommendation not in recommendations:
                recommendations.append(recommendation)
            score -= 10
        elif log["type"] == "CONSOLE" and log["status"] == "error":
            frontend_errors.append(log['target'])
            recommendation = "Frontend console errors detected. Check Javascript logic or missing resources."
            if recommendation not in recommendations:
                recommendations.append(recommendation)
            score-=15
    score= max(score, 0)
    print("\n=== FLOWRA ANALYSIS ===")
    print("\nFrontend Errors:")
    
    for error in frontend_errors:
        print(f"- {error}")
    print("\nInteraction Issues:")
    for issue in interaction_issues:
        print(f"- {issue}")

    print(f"\nOverall Score: {score}/100")
    if score >= 90:
        grade = "Excellent"
    elif score >= 70:
        grade = "Good"
    elif score >= 50:
        grade = "Needs Improvement"
    else:
        grade = "Critical"
    print(f"\nExecution Time: {execution_time} seconds")

    summary["score"] = score
    summary["grade"] = grade
    summary["frontend_errors"] = frontend_errors
    summary["interaction_issues"] = interaction_issues
    summary["recommendations"] = recommendations
    summary["execution_time"] = execution_time

    return summary


with sync_playwright() as p:
    track("SYSTEM", "browser launch", "success")
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    page.on(
        "console",
        lambda msg: track(
            "CONSOLE",
            msg.text,
            msg.type,
            "FRONTEND_ERROR"
        )
    )
    
    page.goto("http://127.0.0.1:5500/test.html")
    track("NAVIGATION", "login page", "success")
    # Page loaded here
    analyze_inputs(page)
    start = time.time()
    original_url = page.url
    
    analyze_buttons(page, original_url)
    end = time.time()
    execution_time = round(end - start, 2)
    page.wait_for_timeout(15000)        

print("\nSESSION LOGS:\n")

summary = generate_summary(execution_time)
report = {
    "logs": logs,
    "summary": summary
}
with open("session_report.json", "w") as f:
    json.dump(report, f, indent=4)
print(summary)