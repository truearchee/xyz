import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { SortableHeader } from "./SortableHeader";
import { Table } from "./Table";

describe("Table — static a11y (§6.4)", () => {
  it("renders a semantic <table> with a button-based sortable header", () => {
    render(
      <Table caption="Users">
        <thead>
          <tr>
            <SortableHeader label="Name" direction="ascending" />
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Ada</td>
          </tr>
        </tbody>
      </Table>,
    );
    expect(screen.getByRole("table")).toBeTruthy();

    const sortBtn = screen.getByRole("button", { name: /Name/ });
    expect(sortBtn.tagName).toBe("BUTTON");

    const colHeader = screen.getByRole("columnheader");
    expect(colHeader.getAttribute("aria-sort")).toBe("ascending");
  });
});
