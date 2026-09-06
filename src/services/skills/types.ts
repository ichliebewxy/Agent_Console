export type SkillInfo = {
  name: string;
  description: string;
  path: string;
  resources: number;
};
export type SkillMeta = Pick<SkillInfo, "name" | "description">;
