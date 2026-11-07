export function withSessionDeadline<T>(operation: Promise<T>, milliseconds = 10000): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("Your sign-in session could not be checked in time. Please try again.")), milliseconds);
    operation.then((value) => { clearTimeout(timer); resolve(value); }, (error) => { clearTimeout(timer); reject(error); });
  });
}
