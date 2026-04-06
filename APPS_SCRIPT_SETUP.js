/**
 * TAR Cost Control - Google Apps Script Data API
 *
 * SETUP INSTRUCTIONS:
 * 1. Open the Google Sheet: https://docs.google.com/spreadsheets/d/1iJmrfFlFX9_FNlrZlMLi1ZofHQPZ1x7OMdTwTX-Q_78/edit
 * 2. Go to Extensions > Apps Script
 * 3. Delete any existing code in Code.gs
 * 4. Paste this entire script into Code.gs
 * 5. Click Save (Ctrl+S)
 * 6. Click Deploy > New deployment
 * 7. Select type: "Web app"
 * 8. Set "Execute as": Me (your email)
 * 9. Set "Who has access": Anyone
 * 10. Click Deploy
 * 11. Authorize when prompted (click through the "unsafe" warning)
 * 12. Copy the Web app URL — paste it into the Streamlit app sidebar
 *
 * The URL will look like:
 * https://script.google.com/macros/s/XXXXXXXXX/exec
 */

function doGet(e) {
  var action = (e && e.parameter && e.parameter.action) ? e.parameter.action : "sheets";

  try {
    var ss = SpreadsheetApp.getActiveSpreadsheet();

    if (action === "sheets") {
      // Return list of sheet names
      var sheets = ss.getSheets().map(function(s) { return s.getName(); });
      return jsonResponse({ sheets: sheets });
    }

    if (action === "data") {
      var sheetName = e.parameter.sheet;
      if (!sheetName) {
        return jsonResponse({ error: "Missing 'sheet' parameter" });
      }

      var sheet = ss.getSheetByName(sheetName);
      if (!sheet) {
        return jsonResponse({ error: "Sheet '" + sheetName + "' not found" });
      }

      var data = sheet.getDataRange().getValues();
      return jsonResponse({ sheet: sheetName, data: data, rows: data.length, cols: data[0].length });
    }

    if (action === "gate") {
      // Optimized: return Gate Time Data with only needed columns
      var sheet = ss.getSheetByName("Gate Time Data");
      if (!sheet) {
        return jsonResponse({ error: "Sheet 'Gate Time Data' not found" });
      }
      var data = sheet.getDataRange().getValues();
      return jsonResponse({ sheet: "Gate Time Data", data: data, rows: data.length });
    }

    if (action === "rates") {
      // Return Rate_Table
      var sheet = ss.getSheetByName("Rate_Table");
      if (!sheet) {
        return jsonResponse({ error: "Sheet 'Rate_Table' not found" });
      }
      var data = sheet.getDataRange().getValues();
      return jsonResponse({ sheet: "Rate_Table", data: data, rows: data.length });
    }

    if (action === "all") {
      // Return both gate data and rate table in one call
      var gateSheet = ss.getSheetByName("Gate Time Data");
      var rateSheet = ss.getSheetByName("Rate_Table");

      var result = {};

      if (gateSheet) {
        result.gate = gateSheet.getDataRange().getValues();
        result.gateRows = result.gate.length;
      } else {
        result.gateError = "Sheet 'Gate Time Data' not found";
      }

      if (rateSheet) {
        result.rates = rateSheet.getDataRange().getValues();
        result.rateRows = result.rates.length;
      } else {
        result.rateError = "Sheet 'Rate_Table' not found";
      }

      return jsonResponse(result);
    }

    return jsonResponse({ error: "Unknown action: " + action, available: ["sheets", "data", "gate", "rates", "all"] });

  } catch (err) {
    return jsonResponse({ error: err.toString() });
  }
}

function jsonResponse(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
