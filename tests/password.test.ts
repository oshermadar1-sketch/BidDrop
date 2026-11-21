// Password and email rules shown on the sign-up, reset and set-password forms.
import { PASSWORD_RULES, passwordIsStrong, emailLooksValid, MIN_LENGTH } from "../lib/password";

describe("password rules", () => {
  test("a password that meets every rule is strong", () => {
    expect(passwordIsStrong("Biddrop2026")).toBe(true);
  });

  test.each([
    ["too short", "Ab1"],
    ["no upper-case letter", "biddrop2026"],
    ["no lower-case letter", "BIDDROP2026"],
    ["no digit", "BiddropDemo"],
  ])("rejects a password with %s", (_why, password) => {
    expect(passwordIsStrong(password)).toBe(false);
  });

  test("each rule reports its own failure", () => {
    const byKey = Object.fromEntries(PASSWORD_RULES.map((r) => [r.key, r.ok("abc")]));
    expect(byKey).toEqual({ length: false, upper: false, lower: true, digit: false });
  });

  test("the length rule uses the shared minimum", () => {
    const length = PASSWORD_RULES.find((r) => r.key === "length")!;
    expect(length.ok("x".repeat(MIN_LENGTH - 1))).toBe(false);
    expect(length.ok("x".repeat(MIN_LENGTH))).toBe(true);
  });
});

describe("email check", () => {
  test.each(["gal@example.com", "  gal@example.com  ", "a.b+c@sub.domain.co.il"])(
    "accepts %s",
    (email) => expect(emailLooksValid(email)).toBe(true)
  );

  test.each(["", "gal", "gal@", "@example.com", "gal@example", "gal example@site.com"])(
    "rejects %j",
    (email) => expect(emailLooksValid(email)).toBe(false)
  );
});
