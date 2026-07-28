export type StaffAnnouncement = {
  id: number;
  title: string;
  message: string;
  author_id: number;
  author_username: string;
  created_at: string;
  starred: boolean;
};

export type AnnouncementWsEvent = {
  event: 'announcement';
  action: 'created';
  announcement: StaffAnnouncement;
};
