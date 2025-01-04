import { createLazyFileRoute } from "@tanstack/react-router";

export const Route = createLazyFileRoute("/about")({
    component: About,
});

function About() {
    return <div>Hello from About!</div>;
}
