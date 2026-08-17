import { useRef, useState, type ChangeEvent, type FormEvent, type KeyboardEvent } from "react";
import styles from "./SessionJoinForm.module.css";

const CODE_LENGTH = 6;

interface SessionJoinFormProps {
  onJoin: (sessionId: string) => void;
}

export function SessionJoinForm({ onJoin }: SessionJoinFormProps) {
  const [digits, setDigits] = useState<string[]>(Array(CODE_LENGTH).fill(""));
  const inputRefs = useRef<Array<HTMLInputElement | null>>([]);

  function handleChange(index: number, event: ChangeEvent<HTMLInputElement>) {
    const value = event.target.value.toUpperCase().slice(-1);
    if (value && !/^[A-Z0-9]$/.test(value)) return;

    const next = [...digits];
    next[index] = value;
    setDigits(next);

    if (value && index < CODE_LENGTH - 1) {
      inputRefs.current[index + 1]?.focus();
    }
  }

  function handleKeyDown(index: number, event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Backspace" && !digits[index] && index > 0) {
      inputRefs.current[index - 1]?.focus();
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const code = digits.join("");
    if (code.length === CODE_LENGTH) {
      onJoin(code);
    }
  }

  const isComplete = digits.every((digit) => digit.length === 1);

  return (
    <form className={styles.form} onSubmit={handleSubmit}>
      <p className={styles.eyebrow}>Enter session code</p>
      <div className={styles.digits} role="group" aria-label="Session code">
        {digits.map((digit, index) => (
          <input
            key={index}
            ref={(el) => {
              inputRefs.current[index] = el;
            }}
            className={styles.digit}
            value={digit}
            onChange={(event) => handleChange(index, event)}
            onKeyDown={(event) => handleKeyDown(index, event)}
            maxLength={1}
            inputMode="text"
            autoCapitalize="characters"
            aria-label={`Digit ${index + 1} of ${CODE_LENGTH}`}
          />
        ))}
      </div>
      <button className={styles.submit} type="submit" disabled={!isComplete}>
        Connect →
      </button>
      <p className={styles.caption}>Your code lives on the host device.</p>
    </form>
  );
}
