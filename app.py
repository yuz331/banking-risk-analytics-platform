"""Local synthetic transaction-monitoring dashboard and analyst review workflow."""

import os
import sqlite3
import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from dashboard_data import alert_queue, cad, overview, queue_csv
from review_alerts import ReviewConflict, ensure_review_schema, review_history, save_review
from show_alerts import read_alerts

st.set_page_config(page_title="Banking Risk Analytics", page_icon="🏦", layout="wide")


def main():
    st.title("Banking Risk Analytics")
    st.caption("SYNTHETIC DATA · Educational transaction monitoring · Human review required")
    with st.sidebar:
        st.header("Workspace")
        db_text = st.text_input("Database path", value=os.environ.get("BANKING_RISK_DB", "data/banking.db"), key="db_path")
        refreshed = st.button("Refresh data", key="refresh")
        st.divider()
        st.subheader("Alert queue filters")
        st.caption("These filters affect the queue and its export. Overview charts use the full snapshot.")
        rule = st.selectbox("Rule", ["All", "R001", "R002", "R003", "R004"], key="rule_filter")
        priority = st.selectbox("Priority", ["All", "HIGH", "MEDIUM", "LOW"], key="priority_filter")
        status = st.selectbox("Status", ["All", "NEW", "IN_REVIEW", "CLOSED"], key="status_filter")
        account = st.text_input("Account ID", placeholder="e.g. A00004", key="account_filter").strip().upper()
    db_path = Path(db_text).expanduser()
    if not db_path.is_absolute():
        db_path = ROOT / db_path
    try:
        ensure_review_schema(db_path)
        data = overview(db_path)
    except (OSError, sqlite3.Error, ValueError) as error:
        st.error(f"Unable to open this snapshot: {error}")
        st.info("Prepare the four-rule demo in a terminal, then set Database path to data/demo_run/banking.db.")
        st.code("python3 run_demo.py --prepare-only", language="bash")
        return

    if "review_flash" in st.session_state:
        st.success(st.session_state.pop("review_flash"))
    summary = data["summary"]
    st.caption(f"Transaction coverage: {summary['first_time'] or 'No records'} to {summary['last_time'] or 'No records'} UTC · "
               f"Latest saved detection: {summary['latest_detection_utc'] or 'Not run'} UTC")
    metrics = st.columns(4)
    for column, label, value in zip(metrics, ("Posted transactions", "Saved alerts", "Open alerts", "Closed alerts"),
                                    (summary["posted_transactions"] or 0, summary["alerts"], summary["open_alerts"], summary["closed_alerts"])):
        column.metric(label, f"{value:,}")
    st.caption(f"Open = NEW + IN_REVIEW · {summary['review_records']} saved review records · Alerts may include multiple rule configurations.")

    st.subheader("Transaction activity")
    st.caption(f"Posted flows only · Inbound {cad(summary['inbound_cents'])} · Outbound {cad(summary['outbound_cents'])} · These flows are not account balances.")
    if data["daily"]:
        daily = pd.DataFrame(data["daily"])
        daily["day_utc"] = pd.to_datetime(daily["day_utc"])
        chart = alt.Chart(daily).mark_area(color="#17695E", opacity=0.2, line=True).encode(
            x=alt.X("day_utc:T", title="UTC date"), y=alt.Y("transaction_count:Q", title="Posted transactions"),
            tooltip=[alt.Tooltip("day_utc:T", title="UTC day", format="%b %d, %Y"), alt.Tooltip("transaction_count:Q", title="Transactions", format=",")]
        ).properties(height=230)
        st.altair_chart(chart, width="stretch")
    else:
        st.info("No posted transactions in this snapshot.")
    left, right = st.columns([2, 1])
    with left:
        st.subheader("Alerts by rule and status")
        if data["distribution"]:
            distribution = pd.DataFrame(data["distribution"])
            st.altair_chart(alt.Chart(distribution).mark_bar().encode(
                x=alt.X("rule_id:N", title="Rule"), y=alt.Y("alert_count:Q", title="Saved alerts"),
                color=alt.Color("status:N", scale=alt.Scale(domain=["NEW", "IN_REVIEW", "CLOSED"], range=["#5689AC", "#DBA24C", "#17695E"])),
                tooltip=["rule_id:N", "status:N", "alert_count:Q"]
            ).properties(height=220), width="stretch")
        else:
            st.info("No saved alerts. Run detection to populate the queue.")
    with right:
        st.subheader("Interpretation")
        st.write("Alerts indicate patterns for review. They do not establish fraud or a reporting obligation.")
        st.write("R001 and R004 skip transactions with insufficient history. No alert does not mean an account was cleared.")
        with st.expander("Rule guide"):
            st.write("R001 · Unusual amount\n\nR002 · High velocity\n\nR003 · Rapid incoming/outgoing funds\n\nR004 · Unusual cross-border wire")

    st.divider()
    st.subheader("Analyst queue")
    filters = {"rule": None if rule == "All" else rule, "priority": None if priority == "All" else priority,
               "status": None if status == "All" else status, "account": account or None}
    queue = alert_queue(db_path, **filters)
    page_count = max(1, (queue["total"] + 24) // 25)
    page = st.selectbox("Queue page", list(range(1, page_count + 1)), key=f"page_{db_path}_{rule}_{priority}_{status}_{account}")
    if page != 1:
        queue = alert_queue(db_path, **filters, page=page - 1)
    st.caption(f"{queue['total']:,} matching alerts · Page {page} of {page_count} · Up to 25 rows per page")
    if not queue["rows"]:
        st.info("No alerts match these filters.")
        return
    st.dataframe(pd.DataFrame(queue["rows"]), hide_index=True, width="stretch", column_order=[
        "rule_id", "account_id", "priority", "score", "status", "event_start_utc", "evidence_count", "alert_id"])
    st.download_button("Download this queue page (CSV)", queue_csv(queue["rows"]), "synthetic_alert_queue_page.csv", "text/csv")
    labels = {row["alert_id"]: f"{row['rule_id']} · {row['account_id']} · {row['priority']} · {row['event_start_utc']} UTC · {row['alert_id'][-8:]}" for row in queue["rows"]}
    selected = st.selectbox("Inspect alert", list(labels), format_func=labels.get, key=f"inspect_{db_path}_{page}_{rule}_{priority}_{status}_{account}")
    alert = read_alerts(db_path, alert_id=selected, with_evidence=True)[0]
    history = review_history(db_path, selected)
    st.subheader("Alert evidence")
    st.write(alert["explanation"])
    st.caption(f"Rule version {alert['rule_version']} · Current status {alert['status']} · Saved {alert['created_time_utc']} UTC")
    with st.expander("Detection parameters and details"):
        st.json({"parameters": alert["parameters"], "details": alert.get("details", {})})
    evidence = pd.DataFrame(alert["transactions"])
    if not evidence.empty:
        evidence["amount_cad"] = evidence["amount_cents"].map(cad)
        st.dataframe(evidence.drop(columns=["amount_cents"]), hide_index=True, width="stretch")

    st.subheader("Save a review")
    expected = history[0]["review_id"] if history else None
    # Preserve the revision that the displayed form was based on across its submit rerun.
    form_token = f"review_token_{db_path}_{selected}"
    if st.session_state.get(f"shown_{db_path}") != selected or refreshed:
        st.session_state[form_token] = expected
        st.session_state[f"shown_{db_path}"] = selected
    outcome_labels = {"IN_REVIEW": "Continue review", "NO_CONCERN": "Close — no concern found", "ESCALATE": "Close — recommend escalation"}
    with st.form(f"review_{db_path}_{selected}", clear_on_submit=True):
        alias = st.text_input("Reviewer alias", max_chars=60, key=f"alias_{selected}")
        outcome = st.selectbox("Review outcome", list(outcome_labels), format_func=outcome_labels.get, key=f"outcome_{selected}")
        notes = st.text_area("Review notes", max_chars=2000, key=f"notes_{selected}")
        st.caption("Alias is a local label, not authenticated identity. Escalation records a recommendation; it sends nothing.")
        submitted = st.form_submit_button("Save review", type="primary")
    if submitted:
        try:
            new_revision = save_review(db_path, selected, outcome, alias, notes, st.session_state[form_token])
            st.session_state[form_token] = new_revision
            st.session_state["review_flash"] = "Review saved. Queue status and review history updated."
            st.rerun()
        except (ValueError, sqlite3.Error) as error:
            st.error(str(error))
    if history:
        st.subheader("Review history")
        st.dataframe(pd.DataFrame(history).drop(columns=["alert_id"]), hide_index=True, width="stretch")
    else:
        st.caption("No reviews saved for this alert yet.")


if __name__ == "__main__":
    main()
