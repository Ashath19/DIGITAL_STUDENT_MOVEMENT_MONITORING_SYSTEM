CREATE TABLE ⁠ attendance ⁠ (
  ⁠ id ⁠ int PRIMARY KEY NOT NULL AUTO_INCREMENT,
  ⁠ usn ⁠ varchar(50) DEFAULT null,
  ⁠ date ⁠ date DEFAULT null,
  ⁠ departure_time ⁠ time DEFAULT null,
  ⁠ arrival_time ⁠ time DEFAULT null,
  ⁠ destination ⁠ varchar(100) DEFAULT null,
  ⁠ deleted ⁠ tinyint(1) DEFAULT '0'
);

CREATE TABLE ⁠ student_details ⁠ (
  ⁠ id ⁠ int NOT NULL AUTO_INCREMENT,
  ⁠ name ⁠ varchar(100) DEFAULT null,
  ⁠ usn ⁠ varchar(50) DEFAULT null,
  ⁠ batch ⁠ varchar(20) DEFAULT null,
  ⁠ branch ⁠ varchar(50) DEFAULT null,
  ⁠ parent_phone ⁠ varchar(15) DEFAULT null,
  ⁠ student_phone ⁠ varchar(15) DEFAULT null,
  ⁠ address ⁠ text,
  ⁠ father_name ⁠ varchar(100) DEFAULT null,
  ⁠ mother_name ⁠ varchar(100) DEFAULT null,
  ⁠ room_number ⁠ varchar(20) DEFAULT null,
  ⁠ email ⁠ varchar(100) DEFAULT null,
  ⁠ face_registered ⁠ tinyint(1) DEFAULT '0',
  PRIMARY KEY (⁠ id ⁠, ⁠ usn ⁠)
);

CREATE TABLE ⁠ users ⁠ (
  ⁠ id ⁠ int PRIMARY KEY NOT NULL AUTO_INCREMENT,
  ⁠ username ⁠ varchar(50) NOT NULL,
  ⁠ password ⁠ varchar(255) NOT NULL,
  ⁠ role ⁠ ENUM ('Supervisor', 'Admin', 'Warden', 'Attendance Desk') NOT NULL
);

CREATE INDEX ⁠ usn ⁠ ON ⁠ attendance ⁠ (⁠ usn ⁠);

CREATE UNIQUE INDEX ⁠ unique_student ⁠ ON ⁠ student_details ⁠ (⁠ usn ⁠);

CREATE INDEX ⁠ idx_usn ⁠ ON ⁠ student_details ⁠ (⁠ usn ⁠);

CREATE UNIQUE INDEX ⁠ username ⁠ ON ⁠ users ⁠ (⁠ username ⁠);

ALTER TABLE ⁠ attendance ⁠ ADD CONSTRAINT ⁠ attendance_ibfk_1 ⁠ FOREIGN KEY (⁠ usn ⁠) REFERENCES ⁠ student_details ⁠ (⁠ usn ⁠);

INSERT INTO users (username, password, role) VALUES 
('supervisor', 'password1', 'Supervisor'),
('admin', 'password2', 'Admin'),
('warden', 'password3', 'Warden'),
('attendance_desk', 'password4', 'Attendance Desk');

INSERT INTO `` (`id`,`name`,`usn`,`batch`,`branch`,`parent_phone`,`student_phone`,`address`,`father_name`,`mother_name`,`room_number`,`email`,`face_registered`) VALUES (1,'Gurunath','4SU21CS001','2021','CSE','9876543210','8765432109','123 Park Street, Bangalore','Rajesh Kumar','Priya Kumar','A101','rahul.k@example.com',0);
INSERT INTO `` (`id`,`name`,`usn`,`batch`,`branch`,`parent_phone`,`student_phone`,`address`,`father_name`,`mother_name`,`room_number`,`email`,`face_registered`) VALUES (2,'Prabhu Gowda Patil','4SU22AD401','2021','ADE','9876543213','8765432106','321 Valley Road, Pune','Vikram Sharma','Meera Sharma','D404','4su21ad016@sdmit.in',0);
INSERT INTO `` (`id`,`name`,`usn`,`batch`,`branch`,`parent_phone`,`student_phone`,`address`,`father_name`,`mother_name`,`room_number`,`email`,`face_registered`) VALUES (3,'Ashwath G Bhat','4SU21AD009','2021','ADE','9876543214','8765432105','654 Beach Road, Chennai','Peter David','Mary David','E505','john.d@example.com',0);

