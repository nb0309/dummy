// Drive a fixture's own validation so the error state exists in the DOM before
// extract.js snapshots it. 3.3.1 is about errors that appear *after* a submit,
// but element_html/parent_html are captured up front — so without this pass the
// stored HTML would show a pristine form and no error at all.
//
// Fixture contract (both markers are stripped by normalize.js so they never
// reach a feature column):
//   [data-error-fill="<value>"]  seed a control with a value that fails the
//                                page's validation. Optional, repeatable.
//   [data-error-trigger]         the control to click (the submit button). Its
//                                presence is what opts a page into this pass.
//
// Disjoint from the 4.1.3 probe's [data-status-target]/[data-status-trigger], so
// the two never fire on the same fixture and cannot interfere.

/**
 * Fill the marked controls and click the marked trigger. No-op (and no DOM
 * touch at all) on any page without [data-error-trigger], which keeps every
 * pre-existing suite capturing byte-identically.
 *
 * @param {import('@playwright/test').Page} page
 * @param {{settleMs?: number}} opts
 * @returns {Promise<boolean>} true if the page was driven, false if not a 3.3.1 fixture
 */
export async function triggerErrors(page, { settleMs = 100 } = {}) {
  return page.evaluate(
    async ({ settleMs }) => {
      const trigger = document.querySelector("[data-error-trigger]");
      if (!trigger) return false;

      document.querySelectorAll("[data-error-fill]").forEach((el) => {
        const value = el.getAttribute("data-error-fill");
        el.value = value;
        // Assigning .value updates the IDL property but NOT the value content
        // attribute, so it would be absent from outerHTML -- the evidence would
        // show an empty field next to an error message. Mirror it across.
        el.setAttribute("value", value);
        el.dispatchEvent(new Event("input", { bubbles: true }));
        el.dispatchEvent(new Event("change", { bubbles: true }));
      });

      trigger.click();
      // Let the page's submit handler render its error state.
      await new Promise((r) => setTimeout(r, settleMs));
      return true;
    },
    { settleMs }
  );
}
